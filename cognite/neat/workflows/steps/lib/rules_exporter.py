import logging
import time
import warnings
from pathlib import Path
from typing import ClassVar

from cognite.client import data_modeling as dm

import cognite.neat.graph.extractors._graph_capturing_sheet
from cognite.neat.exceptions import wrangle_warnings
from cognite.neat.rules import exporter
from cognite.neat.rules.exporter._rules2dms import DataModel
from cognite.neat.rules.exporter._rules2graphql import GraphQLSchema
from cognite.neat.rules.exporter._rules2ontology import Ontology
from cognite.neat.utils.utils import generate_exception_report
from cognite.neat.workflows._exceptions import StepNotInitialized
from cognite.neat.workflows.model import FlowMessage, StepExecutionStatus
from cognite.neat.workflows.steps.data_contracts import CogniteClient, DMSDataModel, RulesData
from cognite.neat.workflows.steps.step_model import Configurable, Step

__all__ = [
    "DMSDataModelFromRules",
    "GraphQLSchemaFromRules",
    "OntologyFromRules",
    "SHACLFromRules",
    "GraphCaptureSpreadsheetFromRules",
    "UploadDMSDataModel",
    "DeleteDMSDataModel",
    "ExcelFromRules",
    "ExportDMSDataModel",
]

CATEGORY = __name__.split(".")[-1].replace("_", " ").title()


class DMSDataModelFromRules(Step):
    """
    This step generates DMS Data model from data model defined in transformation rules
    """

    description = "This step generates DMS Data model from data model defined in transformation rules."
    category = CATEGORY

    configurables: ClassVar[list[Configurable]] = [
        Configurable(
            name="space",
            value="",
            label=("Space to upload DMS Data model to, if empty defaults to the space defined in Rules"),
        ),
        Configurable(
            name="version",
            value="",
            label=("Version of DMS Data model to upload, if empty defaults to the version defined in Rules"),
        ),
        Configurable(
            name="external_id",
            value="",
            label=("External ID of DMS Data model to upload, if empty defaults to the external ID defined in Rules"),
        ),
    ]

    def run(self, rules: RulesData) -> (FlowMessage, DMSDataModel):  # type: ignore[override, syntax]
        if new_space := self.configs["space"]:
            rules.rules.update_space(new_space)
        if new_version := self.configs["version"]:
            rules.rules.update_version(new_version)
        if new_external_id := self.configs["external_id"]:
            rules.rules.metadata.suffix = new_external_id

        data_model = DataModel.from_rules(rules.rules)

        output_text = (
            f"DMS Data Model <b><code>{data_model.external_id}</code></b> version"
            f" <b><code>{data_model.version}</code></b> generated containing:<ul>"
            f"<li> {len(data_model.containers)} containers</li>"
            f"<li> {len(data_model.views)} views</li>"
            f"</ul> Data model is meant to be uploaded to <b><code>{data_model.space}</code></b> space"
        )

        # need to store the data model in the step so that it can be used by the next step
        # see GraphQL step

        return FlowMessage(output_text=output_text), DMSDataModel(data_model=data_model)


class ExportDMSDataModel(Step):
    """
    This step exports DMS data model and its building components to YAML files
    """

    description = "This step generates GraphQL schema from data model defined in transformation rules."
    category = CATEGORY
    configurables: ClassVar[list[Configurable]] = [
        Configurable(name="storage_dir", value="staging", label="Directory to store DMS schema files"),
        Configurable(
            name="format",
            value="yaml-dump",
            label="Format of the output files",
            options=["yaml-dump", "cognite-toolkit", "all"],
        ),
    ]

    def run(self, data_model_contract: DMSDataModel) -> FlowMessage:  # type: ignore[override, syntax]
        if self.configs is None or self.data_store_path is None:
            raise StepNotInitialized(type(self).__name__)

        staging_dir_str = self.configs["storage_dir"]
        format_ = self.configs["format"]

        staging_dir = self.data_store_path / Path(staging_dir_str)
        staging_dir.mkdir(parents=True, exist_ok=True)

        if format_ in ["yaml-dump", "all"]:
            base_file_name = (
                f"{data_model_contract.data_model.space}-"
                f"{data_model_contract.data_model.external_id}-"
                f"v{data_model_contract.data_model.version.strip().replace('.', '_')}"
            )

            _container_file_name = f"{base_file_name}-containers.yaml"
            _data_model_file_name = f"{base_file_name}-data-model.yaml"

            container_full_path = staging_dir / _container_file_name
            data_model_full_path = staging_dir / _data_model_file_name

            data_model = dm.DataModelApply(
                space=data_model_contract.data_model.space,
                external_id=data_model_contract.data_model.external_id,
                version=data_model_contract.data_model.version,
                description=data_model_contract.data_model.description,
                name=data_model_contract.data_model.name,
                views=list(data_model_contract.data_model.views.values()),
            )

            containers = dm.ContainerApplyList(data_model_contract.data_model.containers.values())

            container_full_path.write_text(containers.dump_yaml())
            data_model_full_path.write_text(data_model.dump_yaml())

            output_text = (
                "<p></p>"
                "DMS Schema exported and can be downloaded here : "
                "<p></p>"
                f'- <a href="/data/{staging_dir_str}/{_data_model_file_name}?{time.time()}" '
                f'target="_blank">{_data_model_file_name}</a>'
                "<p></p>"
                f'- <a href="/data/{staging_dir_str}/{_container_file_name}?{time.time()}" '
                f'target="_blank">{_container_file_name}</a>'
            )

            return FlowMessage(output_text=output_text)
        else:
            return FlowMessage(
                error_text=f"Export format <b><code>{format_}</code></b> not implemented!",
                step_execution_status=StepExecutionStatus.ABORT_AND_FAIL,
            )


class UploadDMSDataModel(Step):
    """
    This step uploaded generated DMS Data model
    """

    description = "This step uploaded generated DMS Data model."
    category = CATEGORY

    def run(self, data_model: DMSDataModel, cdf_client: CogniteClient) -> FlowMessage:  # type: ignore[override, syntax]
        data_model.data_model.to_cdf(cdf_client)

        output_text = (
            f"DMS Data Model <b><code>{data_model.data_model.external_id}</code></b> version"
            f" <b><code>{data_model.data_model.version}</code></b> uploaded to space"
            f" <b><code>{data_model.data_model.space}</code></b> containing:<ul>"
            f"<li> {len(data_model.data_model.containers)} containers</li>"
            f"<li> {len(data_model.data_model.views)} views</li></ul>"
        )

        return FlowMessage(output_text=output_text)


class DeleteDMSDataModel(Step):
    """
    This step deletes DMS Data model and all underlying containers and views
    """

    description = "This step deletes DMS Data model and all underlying containers and views."
    category = CATEGORY

    def run(self, data_model: DMSDataModel, cdf_client: CogniteClient) -> FlowMessage:  # type: ignore[override, syntax]
        data_model.data_model.remove_data_model(cdf_client)

        output_text = (
            f"DMS Data Model {data_model.data_model.external_id} version {data_model.data_model.version} "
            f"under {data_model.data_model.space} removed:"
            f"<p> - {len(data_model.data_model.containers)} containers removed</p>"
            f"<p> - {len(data_model.data_model.views)} views removed</p>"
        )

        output_text = (
            f"DMS Data Model <b><code>{data_model.data_model.external_id}</code></b> version"
            f" <b><code>{data_model.data_model.version}</code></b> removed"
            f" from space <b><code>{data_model.data_model.space}</code></b> as well:"
            f"<ul><li> {len(data_model.data_model.containers)} containers</li>"
            f"<li> {len(data_model.data_model.views)} views</li></ul>"
        )

        return FlowMessage(output_text=output_text)


class GraphQLSchemaFromRules(Step):
    """
    This step generates GraphQL schema from data model defined in transformation rules
    """

    description = "This step generates GraphQL schema from data model defined in transformation rules."
    category = CATEGORY
    configurables: ClassVar[list[Configurable]] = [
        Configurable(
            name="file_name",
            value="",
            label=(
                "Name of the GraphQL schema file it must have .graphql extension,"
                " if empty defaults to form `prefix-version.graphql`"
            ),
        ),
        Configurable(name="storage_dir", value="staging", label="Directory to store GraphQL schema file"),
    ]

    def run(self, transformation_rules: RulesData) -> FlowMessage:  # type: ignore[override, syntax]
        if self.configs is None or self.data_store_path is None:
            raise StepNotInitialized(type(self).__name__)
        data_model_gql = GraphQLSchema.from_rules(transformation_rules.rules, verbose=True).schema

        default_name = (
            f"{transformation_rules.rules.metadata.prefix}-"
            f"v{transformation_rules.rules.metadata.version.strip().replace('.', '_')}"
            ".graphql"
        )

        schema_name = self.configs["file_name"] or default_name

        staging_dir_str = self.configs["storage_dir"]
        staging_dir = self.data_store_path / Path(staging_dir_str)
        staging_dir.mkdir(parents=True, exist_ok=True)
        fdm_model_full_path = staging_dir / schema_name

        fdm_model_full_path.write_text(data_model_gql)

        output_text = (
            "<p></p>"
            "GraphQL Schema generated and can be downloaded here : "
            f'<a href="/data/{staging_dir_str}/{schema_name}?{time.time()}" '
            f'target="_blank">{schema_name}</a>'
        )

        return FlowMessage(output_text=output_text)


class OntologyFromRules(Step):
    """
    This step generates OWL ontology from data model defined in transformation rules
    """

    description = "This step generates OWL ontology from data model defined in transformation rules."
    category = CATEGORY
    configurables: ClassVar[list[Configurable]] = [
        Configurable(
            name="file_name",
            value="",
            label=(
                "Name of the OWL ontology file it must have .ttl extension,"
                " if empty defaults to form `prefix-version-ontology.ttl`"
            ),
        ),
        Configurable(name="storage_dir", value="staging", label="Directory to store the OWL ontology file"),
        Configurable(
            name="store_warnings",
            value="True",
            label="To store warnings while generating ontology",
            options=["True", "False"],
        ),
    ]

    def run(self, transformation_rules: RulesData) -> FlowMessage:  # type: ignore[override, syntax]
        if self.configs is None or self.data_store_path is None:
            raise StepNotInitialized(type(self).__name__)
        # ontology file
        default_name = (
            f"{transformation_rules.rules.metadata.prefix}-"
            f"v{transformation_rules.rules.metadata.version.strip().replace('.', '_')}"
            "-ontology.ttl"
        )

        ontology_file = self.configs["file_name"] or default_name

        storage_dir_str = self.configs["storage_dir"]
        storage_dir = self.data_store_path / storage_dir_str
        storage_dir.mkdir(parents=True, exist_ok=True)

        store_warnings = self.configs["store_warnings"].lower() == "true"

        with warnings.catch_warnings(record=True) as validation_warnings:
            ontology = Ontology.from_rules(transformation_rules=transformation_rules.rules)

        with (storage_dir / ontology_file).open(mode="w") as onto_file:
            onto_file.write(ontology.ontology)

        if store_warnings and validation_warnings:
            with (storage_dir / "report.txt").open(mode="w") as report_file:
                report_file.write(generate_exception_report(wrangle_warnings(validation_warnings), "Warnings"))

        output_text = (
            "<p></p>"
            "Ontology generated and can be downloaded here : "
            f'<a href="/data/{storage_dir_str}/{ontology_file}?{time.time()}" '
            f'target="_blank">{ontology_file}</a>'
        )

        output_text += (
            (
                "<p></p>"
                " Download conversion report "
                f'<a href="/data/{storage_dir_str}/report.txt?{time.time()}" '
                f'target="_blank">here</a>'
            )
            if validation_warnings
            else ""
        )

        return FlowMessage(output_text=output_text)


class SHACLFromRules(Step):
    """
    This step generates SHACL from data model defined in transformation rules
    """

    description = "This step generates SHACL from data model defined in transformation rules"
    category = CATEGORY
    configurables: ClassVar[list[Configurable]] = [
        Configurable(
            name="file_name",
            value="",
            label=(
                "Name of the SHACL file it must have .ttl extension, if "
                "empty defaults to form `prefix-version-shacl.ttl`"
            ),
        ),
        Configurable(name="storage_dir", value="staging", label="Directory to store the SHACL file"),
    ]

    def run(self, transformation_rules: RulesData) -> FlowMessage:  # type: ignore[override, syntax]
        if self.configs is None or self.data_store_path is None:
            raise StepNotInitialized(type(self).__name__)
        # ontology file
        default_name = (
            f"{transformation_rules.rules.metadata.prefix}-"
            f"v{transformation_rules.rules.metadata.version.strip().replace('.', '_')}"
            "-shacl.ttl"
        )

        shacl_file = self.configs["file_name"] or default_name

        storage_dir_str = self.configs["storage_dir"]
        storage_dir = self.data_store_path / storage_dir_str
        storage_dir.mkdir(parents=True, exist_ok=True)

        constraints = Ontology.from_rules(transformation_rules=transformation_rules.rules).constraints

        with (storage_dir / shacl_file).open(mode="w") as onto_file:
            onto_file.write(constraints)

        output_text = (
            "<p></p>"
            "SHACL generated and can be downloaded here : "
            f'<a href="/data/{storage_dir_str}/{shacl_file}?{time.time()}" '
            f'target="_blank">{shacl_file}</a>'
        )
        return FlowMessage(output_text=output_text)


class GraphCaptureSpreadsheetFromRules(Step):
    """
    This step generates data capture spreadsheet from data model defined in rules
    """

    description = "This step generates data capture spreadsheet from data model defined in rules"
    category = CATEGORY
    configurables: ClassVar[list[Configurable]] = [
        Configurable(name="file_name", value="graph_capture_sheet.xlsx", label="File name of the data capture sheet"),
        Configurable(name="auto_identifier_type", value="index-based", label="Type of automatic identifier"),
        Configurable(name="storage_dir", value="staging", label="Directory to store data capture sheets"),
    ]

    def run(self, rules: RulesData) -> FlowMessage:  # type: ignore[override, syntax]
        if self.configs is None or self.data_store_path is None:
            raise StepNotInitialized(type(self).__name__)
        logging.info("Generate graph capture sheet")
        sheet_name = self.configs["file_name"]
        auto_identifier_type = self.configs["auto_identifier_type"]
        staging_dir_str = self.configs["storage_dir"]
        logging.info(f"Auto identifier type {auto_identifier_type}")
        staging_dir = self.data_store_path / Path(staging_dir_str)
        staging_dir.mkdir(parents=True, exist_ok=True)
        data_capture_sheet_path = staging_dir / sheet_name

        cognite.neat.graph.extractors._graph_capturing_sheet.rules2graph_capturing_sheet(
            rules.rules, data_capture_sheet_path, auto_identifier_type=auto_identifier_type
        )

        output_text = (
            "Data capture sheet generated and can be downloaded here : "
            f'<a href="/data/{staging_dir_str}/{sheet_name}?{time.time()}" target="_blank">'
            f"{sheet_name}</a>"
        )
        return FlowMessage(output_text=output_text)


class ExcelFromRules(Step):
    description = "This step generates Excel file from rules"
    category = CATEGORY
    version = "0.1.0-alpha"
    configurables: ClassVar[list[Configurable]] = [
        Configurable(
            name="output_file_path", value="rules/custom-rules.xlsx", label="File path to the generated Excel file"
        )
    ]

    def run(self, rules_data: RulesData) -> FlowMessage:  # type: ignore[override, syntax]
        full_path = Path(self.data_store_path) / Path(self.configs["output_file_path"])
        exporter.ExcelExporter.from_rules(rules=rules_data.rules).export_to_file(filepath=full_path)
        return FlowMessage(output_text="Generated Excel file from rules")
