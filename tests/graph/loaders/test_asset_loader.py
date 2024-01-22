from typing import Any

import pytest
from rdflib import Graph

from cognite.neat.graph.loaders import AssetLoader
from cognite.neat.graph.loaders.core.rdf_to_assets import rdf2assets
from cognite.neat.graph.stores import MemoryStore
from cognite.neat.rules.models import Rules


class TestAssetLoader:
    @pytest.mark.freeze_time("2024-01-01")
    def test_vs_existing(self, transformation_rules: Rules, solution_knowledge_graph: Graph):
        store = MemoryStore(solution_knowledge_graph)
        loader = AssetLoader(transformation_rules, store, data_set_id=123456)

        loaded = list(loader.load_assets(stop_on_exception=False))

        expected_assets = rdf2assets(store, transformation_rules, data_set_id=123456, stop_on_exception=False)

        actual_dumped: dict[str, dict[str, Any]] = {}
        for asset in loaded:
            dumped = asset.dump(camel_case=False)
            if asset.labels:
                dumped["labels"] = [label.external_id for label in asset.labels]
            if "description" not in dumped:
                dumped["description"] = None
            if "parent_external_id" not in dumped:
                dumped["parent_external_id"] = None
            actual_dumped[asset.external_id] = dumped

        missing = set(expected_assets.keys()) - set(actual_dumped.keys())
        assert not missing, f"Missing {missing}"
        extra = set(actual_dumped.keys()) - set(expected_assets.keys())
        assert not extra, f"Extra {extra}"

        for external_id, expected_asset in expected_assets.items():
            actual_asset = actual_dumped[external_id]
            assert actual_asset == expected_asset
