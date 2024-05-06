import math
import re
import sys
import warnings
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from cognite.client import data_modeling as dm
from pydantic import Field, field_serializer, field_validator, model_serializer, model_validator
from pydantic_core.core_schema import SerializationInfo, ValidationInfo

import cognite.neat.rules.issues.spreadsheet
from cognite.neat.rules import issues
from cognite.neat.rules.models._base import (
    BaseMetadata,
    BaseRules,
    DataModelType,
    ExtensionCategory,
    RoleTypes,
    SchemaCompleteness,
    SheetEntity,
    SheetList,
)
from cognite.neat.rules.models._types import (
    ExternalIdType,
    PropertyType,
    StrListType,
    VersionType,
)
from cognite.neat.rules.models.data_types import DataType
from cognite.neat.rules.models.domain import DomainRules
from cognite.neat.rules.models.entities import (
    ClassEntity,
    ContainerEntity,
    ContainerEntityList,
    DMSUnknownEntity,
    ReferenceEntity,
    URLEntity,
    ViewEntity,
    ViewEntityList,
    ViewPropertyEntity,
)
from cognite.neat.rules.models.wrapped_entities import HasDataFilter, NodeTypeFilter

from ._schema import DMSSchema

if TYPE_CHECKING:
    from cognite.neat.rules.models.information._rules import InformationRules

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

_DEFAULT_VERSION = "1"


class DMSMetadata(BaseMetadata):
    role: ClassVar[RoleTypes] = RoleTypes.dms_architect
    data_model_type: DataModelType = Field(DataModelType.solution, alias="dataModelType")
    schema_: SchemaCompleteness = Field(alias="schema")
    extension: ExtensionCategory = ExtensionCategory.addition
    space: ExternalIdType
    name: str | None = Field(
        None,
        description="Human readable name of the data model",
        min_length=1,
        max_length=255,
    )
    description: str | None = Field(None, min_length=1, max_length=1024)
    external_id: ExternalIdType = Field(alias="externalId")
    version: VersionType
    creator: StrListType
    created: datetime = Field(
        description=("Date of the data model creation"),
    )
    updated: datetime = Field(
        description=("Date of the data model update"),
    )

    @field_validator("*", mode="before")
    def strip_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_serializer("schema_", "extension", "data_model_type", when_used="always")
    @staticmethod
    def as_string(value: SchemaCompleteness | ExtensionCategory | DataModelType) -> str:
        return str(value)

    @field_validator("schema_", mode="plain")
    def as_enum_schema(cls, value: str) -> SchemaCompleteness:
        return SchemaCompleteness(value)

    @field_validator("extension", mode="plain")
    def as_enum_extension(cls, value: str) -> ExtensionCategory:
        return ExtensionCategory(value)

    @field_validator("data_model_type", mode="plain")
    def as_enum_model_type(cls, value: str) -> DataModelType:
        return DataModelType(value)

    @field_validator("description", mode="before")
    def nan_as_none(cls, value):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    def as_space(self) -> dm.SpaceApply:
        return dm.SpaceApply(
            space=self.space,
        )

    def as_data_model_id(self) -> dm.DataModelId:
        return dm.DataModelId(space=self.space, external_id=self.external_id, version=self.version)

    def as_data_model(self) -> dm.DataModelApply:
        suffix = f"Creator: {', '.join(self.creator)}"
        if self.description:
            description = f"{self.description} Creator: {', '.join(self.creator)}"
        else:
            description = suffix

        return dm.DataModelApply(
            space=self.space,
            external_id=self.external_id,
            name=self.name or None,
            version=self.version or "missing",
            description=description,
            views=[],
        )

    @classmethod
    def _get_description_and_creator(cls, description_raw: str | None) -> tuple[str | None, list[str]]:
        if description_raw and (description_match := re.search(r"Creator: (.+)", description_raw)):
            creator = description_match.group(1).split(", ")
            description = description_raw.replace(description_match.string, "").strip() or None
        elif description_raw:
            creator = ["MISSING"]
            description = description_raw
        else:
            creator = ["MISSING"]
            description = None
        return description, creator

    @classmethod
    def from_data_model(cls, data_model: dm.DataModelApply) -> "DMSMetadata":
        description, creator = cls._get_description_and_creator(data_model.description)
        return cls(
            schema_=SchemaCompleteness.complete,
            space=data_model.space,
            name=data_model.name or None,
            description=description,
            external_id=data_model.external_id,
            version=data_model.version,
            creator=creator,
            created=datetime.now(),
            updated=datetime.now(),
        )


class DMSProperty(SheetEntity):
    view: ViewEntity = Field(alias="View")
    view_property: str = Field(alias="View Property")
    name: str | None = Field(alias="Name", default=None)
    description: str | None = Field(alias="Description", default=None)
    connection: Literal["direct", "edge", "reverse"] | None = Field(None, alias="Connection")
    value_type: DataType | ViewPropertyEntity | ViewEntity | DMSUnknownEntity = Field(alias="Value Type")
    nullable: bool | None = Field(default=None, alias="Nullable")
    is_list: bool | None = Field(default=None, alias="Is List")
    default: str | int | dict | None = Field(None, alias="Default")
    reference: URLEntity | ReferenceEntity | None = Field(default=None, alias="Reference", union_mode="left_to_right")
    container: ContainerEntity | None = Field(None, alias="Container")
    container_property: str | None = Field(None, alias="Container Property")
    index: StrListType | None = Field(None, alias="Index")
    constraint: StrListType | None = Field(None, alias="Constraint")
    class_: ClassEntity = Field(alias="Class (linage)")
    property_: PropertyType = Field(alias="Property (linage)")

    @field_validator("nullable")
    def direct_relation_must_be_nullable(cls, value: Any, info: ValidationInfo) -> None:
        if info.data.get("connection") == "direct" and value is False:
            raise ValueError("Direct relation must be nullable")
        return value

    @field_validator("value_type", mode="after")
    def connections_value_type(
        cls, value: ViewPropertyEntity | ViewEntity | DMSUnknownEntity, info: ValidationInfo
    ) -> DataType | ViewPropertyEntity | ViewEntity | DMSUnknownEntity:
        if (connection := info.data.get("connection")) is None:
            return value
        if connection == "direct" and not isinstance(value, ViewEntity | DMSUnknownEntity):
            raise ValueError(f"Direct relation must have a value type that points to a view, got {value}")
        elif connection == "edge" and not isinstance(value, ViewEntity):
            raise ValueError(f"Edge connection must have a value type that points to a view, got {value}")
        elif connection == "reverse" and not isinstance(value, ViewPropertyEntity | ViewEntity):
            raise ValueError(
                f"Reverse connection must have a value type that points to a view or view property, got {value}"
            )
        return value

    @field_serializer("value_type", when_used="always")
    @staticmethod
    def as_dms_type(value_type: DataType | ViewPropertyEntity | ViewEntity) -> str:
        if isinstance(value_type, DataType):
            return value_type.dms._type
        else:
            return str(value_type)


class DMSContainer(SheetEntity):
    container: ContainerEntity = Field(alias="Container")
    name: str | None = Field(alias="Name", default=None)
    description: str | None = Field(alias="Description", default=None)
    reference: URLEntity | ReferenceEntity | None = Field(alias="Reference", default=None, union_mode="left_to_right")
    constraint: ContainerEntityList | None = Field(None, alias="Constraint")
    class_: ClassEntity = Field(alias="Class (linage)")

    def as_container(self) -> dm.ContainerApply:
        container_id = self.container.as_id()
        constraints: dict[str, dm.Constraint] = {}
        for constraint in self.constraint or []:
            requires = dm.RequiresConstraint(constraint.as_id())
            constraints[f"{constraint.space}_{constraint.external_id}"] = requires

        return dm.ContainerApply(
            space=container_id.space,
            external_id=container_id.external_id,
            name=self.name or None,
            description=self.description,
            constraints=constraints or None,
            properties={},
        )

    @classmethod
    def from_container(cls, container: dm.ContainerApply) -> "DMSContainer":
        constraints: list[ContainerEntity] = []
        for _, constraint_obj in (container.constraints or {}).items():
            if isinstance(constraint_obj, dm.RequiresConstraint):
                constraints.append(ContainerEntity.from_id(constraint_obj.require))
            # UniquenessConstraint it handled in the properties
        container_entity = ContainerEntity.from_id(container.as_id())
        return cls(
            class_=container_entity.as_class(),
            container=container_entity,
            name=container.name or None,
            description=container.description,
            constraint=constraints or None,
        )


class DMSView(SheetEntity):
    view: ViewEntity = Field(alias="View")
    name: str | None = Field(alias="Name", default=None)
    description: str | None = Field(alias="Description", default=None)
    implements: ViewEntityList | None = Field(None, alias="Implements")
    reference: URLEntity | ReferenceEntity | None = Field(alias="Reference", default=None, union_mode="left_to_right")
    filter_: HasDataFilter | NodeTypeFilter | None = Field(None, alias="Filter")
    in_model: bool = Field(True, alias="In Model")
    class_: ClassEntity = Field(alias="Class (linage)")

    def as_view(self) -> dm.ViewApply:
        view_id = self.view.as_id()
        return dm.ViewApply(
            space=view_id.space,
            external_id=view_id.external_id,
            version=view_id.version or _DEFAULT_VERSION,
            name=self.name or None,
            description=self.description,
            implements=[parent.as_id() for parent in self.implements or []] or None,
            properties={},
        )

    @classmethod
    def from_view(cls, view: dm.ViewApply, in_model: bool) -> "DMSView":
        view_entity = ViewEntity.from_id(view.as_id())
        class_entity = view_entity.as_class(skip_version=True)

        return cls(
            class_=class_entity,
            view=view_entity,
            description=view.description,
            name=view.name,
            implements=[ViewEntity.from_id(parent, _DEFAULT_VERSION) for parent in view.implements] or None,
            in_model=in_model,
        )


class DMSRules(BaseRules):
    metadata: DMSMetadata = Field(alias="Metadata")
    properties: SheetList[DMSProperty] = Field(alias="Properties")
    views: SheetList[DMSView] = Field(alias="Views")
    containers: SheetList[DMSContainer] | None = Field(None, alias="Containers")
    reference: "DMSRules | None" = Field(None, alias="Reference")

    @field_validator("reference")
    def check_reference_of_reference(cls, value: "DMSRules | None", info: ValidationInfo) -> "DMSRules | None":
        if value is None:
            return None
        if value.reference is not None:
            raise ValueError("Reference rules cannot have a reference")
        if value.metadata.data_model_type == DataModelType.solution and (metadata := info.data.get("metadata")):
            warnings.warn(
                issues.dms.SolutionOnTopOfSolutionModelWarning(
                    metadata.as_data_model_id(), value.metadata.as_data_model_id()
                ),
                stacklevel=2,
            )
        return value

    @field_validator("views")
    def matching_version_and_space(cls, value: SheetList[DMSView], info: ValidationInfo) -> SheetList[DMSView]:
        if not (metadata := info.data.get("metadata")):
            return value
        model_version = metadata.version
        if different_version := [view.view.as_id() for view in value if view.view.version != model_version]:
            warnings.warn(issues.dms.ViewModelVersionNotMatchingWarning(different_version, model_version), stacklevel=2)
        if different_space := [view.view.as_id() for view in value if view.view.space != metadata.space]:
            warnings.warn(issues.dms.ViewModelSpaceNotMatchingWarning(different_space, metadata.space), stacklevel=2)
        return value

    @field_validator("views")
    def matching_version(cls, value: SheetList[DMSView], info: ValidationInfo) -> SheetList[DMSView]:
        if not (metadata := info.data.get("metadata")):
            return value
        model_version = metadata.version
        if different_version := [view.view.as_id() for view in value if view.view.version != model_version]:
            warnings.warn(issues.dms.ViewModelVersionNotMatchingWarning(different_version, model_version), stacklevel=2)
        return value

    @model_validator(mode="after")
    def consistent_container_properties(self) -> "DMSRules":
        container_properties_by_id: dict[tuple[ContainerEntity, str], list[tuple[int, DMSProperty]]] = defaultdict(list)
        for prop_no, prop in enumerate(self.properties):
            if prop.container and prop.container_property:
                container_properties_by_id[(prop.container, prop.container_property)].append((prop_no, prop))

        errors: list[cognite.neat.rules.issues.spreadsheet.InconsistentContainerDefinitionError] = []
        for (container, prop_name), properties in container_properties_by_id.items():
            if len(properties) == 1:
                continue
            container_id = container.as_id()
            row_numbers = {prop_no for prop_no, _ in properties}
            value_types = {prop.value_type for _, prop in properties if prop.value_type}
            if len(value_types) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiValueTypeError(
                        container_id,
                        prop_name,
                        row_numbers,
                        {v.dms._type if isinstance(v, DataType) else str(v) for v in value_types},
                    )
                )
            list_definitions = {prop.is_list for _, prop in properties if prop.is_list is not None}
            if len(list_definitions) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiValueIsListError(
                        container_id, prop_name, row_numbers, list_definitions
                    )
                )
            nullable_definitions = {prop.nullable for _, prop in properties if prop.nullable is not None}
            if len(nullable_definitions) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiNullableError(
                        container_id, prop_name, row_numbers, nullable_definitions
                    )
                )
            default_definitions = {prop.default for _, prop in properties if prop.default is not None}
            if len(default_definitions) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiDefaultError(
                        container_id, prop_name, row_numbers, list(default_definitions)
                    )
                )
            index_definitions = {",".join(prop.index) for _, prop in properties if prop.index is not None}
            if len(index_definitions) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiIndexError(
                        container_id, prop_name, row_numbers, index_definitions
                    )
                )
            constraint_definitions = {
                ",".join(prop.constraint) for _, prop in properties if prop.constraint is not None
            }
            if len(constraint_definitions) > 1:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.MultiUniqueConstraintError(
                        container_id, prop_name, row_numbers, constraint_definitions
                    )
                )

            # This sets the container definition for all the properties where it is not defined.
            # This allows the user to define the container only once.
            value_type = next(iter(value_types))
            list_definition = next(iter(list_definitions)) if list_definitions else None
            nullable_definition = next(iter(nullable_definitions)) if nullable_definitions else None
            default_definition = next(iter(default_definitions)) if default_definitions else None
            index_definition = next(iter(index_definitions)).split(",") if index_definitions else None
            constraint_definition = next(iter(constraint_definitions)).split(",") if constraint_definitions else None
            for _, prop in properties:
                prop.value_type = value_type
                prop.is_list = prop.is_list or list_definition
                prop.nullable = prop.nullable or nullable_definition
                prop.default = prop.default or default_definition
                prop.index = prop.index or index_definition
                prop.constraint = prop.constraint or constraint_definition

        if errors:
            raise issues.MultiValueError(errors)
        return self

    @model_validator(mode="after")
    def referenced_views_and_containers_are_existing(self) -> "DMSRules":
        # There two checks are done in the same method to raise all the errors at once.
        defined_views = {view.view.as_id() for view in self.views}

        errors: list[issues.NeatValidationError] = []
        for prop_no, prop in enumerate(self.properties):
            if prop.view and (view_id := prop.view.as_id()) not in defined_views:
                errors.append(
                    cognite.neat.rules.issues.spreadsheet.NonExistingViewError(
                        column="View",
                        row=prop_no,
                        type="value_error.missing",
                        view_id=view_id,
                        msg="",
                        input=None,
                        url=None,
                    )
                )
        if self.metadata.schema_ is SchemaCompleteness.complete:
            defined_containers = {container.container.as_id() for container in self.containers or []}
            for prop_no, prop in enumerate(self.properties):
                if prop.container and (container_id := prop.container.as_id()) not in defined_containers:
                    errors.append(
                        cognite.neat.rules.issues.spreadsheet.NonExistingContainerError(
                            column="Container",
                            row=prop_no,
                            type="value_error.missing",
                            container_id=container_id,
                            msg="",
                            input=None,
                            url=None,
                        )
                    )
            for _container_no, container in enumerate(self.containers or []):
                for constraint_no, constraint in enumerate(container.constraint or []):
                    if constraint.as_id() not in defined_containers:
                        errors.append(
                            cognite.neat.rules.issues.spreadsheet.NonExistingContainerError(
                                column="Constraint",
                                row=constraint_no,
                                type="value_error.missing",
                                container_id=constraint.as_id(),
                                msg="",
                                input=None,
                                url=None,
                            )
                        )
        if errors:
            raise issues.MultiValueError(errors)
        return self

    @model_validator(mode="after")
    def validate_extension(self) -> "DMSRules":
        if self.metadata.schema_ is not SchemaCompleteness.extended:
            return self
        if not self.reference:
            raise ValueError("The schema is set to 'extended', but no reference rules are provided to validate against")
        is_solution = self.metadata.space != self.reference.metadata.space
        if is_solution:
            return self
        if self.metadata.extension is ExtensionCategory.rebuild:
            # Everything is allowed
            return self
        # Is an extension of an existing model.
        user_schema = self.as_schema(include_ref=False)
        ref_schema = self.reference.as_schema()
        new_containers = {container.as_id(): container for container in user_schema.containers}
        existing_containers = {container.as_id(): container for container in ref_schema.containers}

        errors: list[issues.NeatValidationError] = []
        for container_id, container in new_containers.items():
            existing_container = existing_containers.get(container_id)
            if not existing_container or existing_container == container:
                # No problem
                continue
            new_dumped = container.dump()
            existing_dumped = existing_container.dump()
            changed_attributes, changed_properties = self._changed_attributes_and_properties(
                new_dumped, existing_dumped
            )
            errors.append(
                issues.dms.ChangingContainerError(
                    container_id=container_id,
                    changed_properties=changed_properties or None,
                    changed_attributes=changed_attributes or None,
                )
            )

        if self.metadata.extension is ExtensionCategory.reshape and errors:
            raise issues.MultiValueError(errors)
        elif self.metadata.extension is ExtensionCategory.reshape:
            # Reshape allows changes to views
            return self

        new_views = {view.as_id(): view for view in user_schema.views}
        existing_views = {view.as_id(): view for view in ref_schema.views}
        for view_id, view in new_views.items():
            existing_view = existing_views.get(view_id)
            if not existing_view or existing_view == view:
                # No problem
                continue
            changed_attributes, changed_properties = self._changed_attributes_and_properties(
                view.dump(), existing_view.dump()
            )
            errors.append(
                issues.dms.ChangingViewError(
                    view_id=view_id,
                    changed_properties=changed_properties or None,
                    changed_attributes=changed_attributes or None,
                )
            )

        if errors:
            raise issues.MultiValueError(errors)
        return self

    @staticmethod
    def _changed_attributes_and_properties(
        new_dumped: dict[str, Any], existing_dumped: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        """Helper method to find the changed attributes and properties between two containers or views."""
        new_attributes = {key: value for key, value in new_dumped.items() if key != "properties"}
        existing_attributes = {key: value for key, value in existing_dumped.items() if key != "properties"}
        changed_attributes = [key for key in new_attributes if new_attributes[key] != existing_attributes.get(key)]
        new_properties = new_dumped.get("properties", {})
        existing_properties = existing_dumped.get("properties", {})
        changed_properties = [prop for prop in new_properties if new_properties[prop] != existing_properties.get(prop)]
        return changed_attributes, changed_properties

    @model_validator(mode="after")
    def validate_schema(self) -> "DMSRules":
        if self.metadata.schema_ is SchemaCompleteness.partial:
            return self
        elif self.metadata.schema_ is SchemaCompleteness.complete:
            rules: DMSRules = self
        elif self.metadata.schema_ is SchemaCompleteness.extended:
            if not self.reference:
                raise ValueError(
                    "The schema is set to 'extended', but no reference rules are provided to validate against"
                )
            # This is an extension of the reference rules, we need to merge the two
            rules = self.model_copy(deep=True)
            rules.properties.extend(self.reference.properties.data)
            existing_views = {view.view.as_id() for view in rules.views}
            rules.views.extend([view for view in self.reference.views if view.view.as_id() not in existing_views])
            if rules.containers and self.reference.containers:
                existing_containers = {container.container.as_id() for container in rules.containers.data}
                rules.containers.extend(
                    [
                        container
                        for container in self.reference.containers
                        if container.container.as_id() not in existing_containers
                    ]
                )
            elif not rules.containers and self.reference.containers:
                rules.containers = self.reference.containers
        else:
            raise ValueError("Unknown schema completeness")

        schema = rules.as_schema()
        errors = schema.validate()
        if errors:
            raise issues.MultiValueError(errors)
        return self

    @model_serializer(mode="wrap", when_used="always")
    def dms_rules_serialization(
        self,
        handler: Callable,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        from ._serializer import _DMSRulesSerializer

        dumped = cast(dict[str, Any], handler(self, info))
        space, version = self.metadata.space, self.metadata.version
        return _DMSRulesSerializer(info, space, version).clean(dumped)

    def as_schema(
        self, include_ref: bool = False, include_pipeline: bool = False, instance_space: str | None = None
    ) -> DMSSchema:
        from ._exporter import _DMSExporter

        return _DMSExporter(self, include_ref, include_pipeline, instance_space).to_schema()

    def as_information_architect_rules(self) -> "InformationRules":
        from ._converter import _DMSRulesConverter

        return _DMSRulesConverter(self).as_information_architect_rules()

    def as_domain_expert_rules(self) -> DomainRules:
        from ._converter import _DMSRulesConverter

        return _DMSRulesConverter(self).as_domain_rules()

    def reference_self(self) -> Self:
        new_rules = self.model_copy(deep=True)
        for prop in new_rules.properties:
            prop.reference = ReferenceEntity(
                prefix=prop.view.prefix, suffix=prop.view.suffix, version=prop.view.version, property=prop.property_
            )
        view: DMSView
        for view in new_rules.views:
            view.reference = ReferenceEntity(
                prefix=view.view.prefix, suffix=view.view.suffix, version=view.view.version
            )
        container: DMSContainer
        for container in new_rules.containers or []:
            container.reference = ReferenceEntity(prefix=container.container.prefix, suffix=container.container.suffix)
        return new_rules
