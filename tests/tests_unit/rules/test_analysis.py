from cognite.neat.rules.analysis import (
    AssetArchitectRulesAnalysis,
    InformationArchitectRulesAnalysis,
)
from cognite.neat.rules.models import AssetRules, InformationRules
from cognite.neat.rules.models.entities import ClassEntity


class TestInformationRulesAnalysis:
    def test_class_parent_pairs(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).class_parent_pairs()) == 26

    def test_classes_with_properties(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).classes_with_properties()) == 20

    def test_class_property_pairs(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).class_property_pairs()) == 20

    def test_defined_classes(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).defined_classes(consider_inheritance=False)) == 20
        assert len(InformationArchitectRulesAnalysis(david_rules).defined_classes(consider_inheritance=True)) == 26

    def test_disconnected_classes(self, david_rules: InformationRules) -> None:
        assert InformationArchitectRulesAnalysis(david_rules).disconnected_classes(consider_inheritance=False) == {
            ClassEntity.load("power:GeoLocation")
        }

    def test_connected_classes(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).connected_classes(consider_inheritance=False)) == 24
        assert len(InformationArchitectRulesAnalysis(david_rules).connected_classes(consider_inheritance=True)) == 25

    def test_get_class_linkage(self, david_rules: InformationRules) -> None:
        assert len(InformationArchitectRulesAnalysis(david_rules).class_linkage(consider_inheritance=False)) == 28
        assert len(InformationArchitectRulesAnalysis(david_rules).class_linkage(consider_inheritance=True)) == 63

    def test_symmetric_pairs(self, david_rules: InformationRules) -> None:
        assert (
            len(
                InformationArchitectRulesAnalysis(david_rules).symmetrically_connected_classes(
                    consider_inheritance=True
                )
            )
            == 0
        )
        assert (
            len(
                InformationArchitectRulesAnalysis(david_rules).symmetrically_connected_classes(
                    consider_inheritance=False
                )
            )
            == 0
        )

    def test_subset_rules(self, david_rules: InformationRules) -> None:
        assert InformationArchitectRulesAnalysis(david_rules).subset_rules(
            {ClassEntity.load("power:GeoLocation")}
        ).classes.data[0].class_ == ClassEntity.load("power:GeoLocation")
        assert (
            len(
                InformationArchitectRulesAnalysis(david_rules)
                .subset_rules({ClassEntity.load("power:GeoLocation")})
                .classes.data
            )
            == 1
        )


class TestAssetRulesAnalysis:
    def test_asset_definitions(self, jimbo_rules: AssetRules) -> None:
        assert len(AssetArchitectRulesAnalysis(jimbo_rules).asset_definition(only_rdfpath=True)) == 6

    def test_relationship_definitions(self, jimbo_rules: AssetRules) -> None:
        assert len(AssetArchitectRulesAnalysis(jimbo_rules).relationship_definition(only_rdfpath=True)) == 4
