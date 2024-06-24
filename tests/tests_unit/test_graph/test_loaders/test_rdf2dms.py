import pytest

from cognite.neat.graph.loaders import DMSLoader
from cognite.neat.graph.stores import NeatGraphStore
from cognite.neat.rules.importers import InferenceImporter
from tests.data import car


@pytest.fixture()
def car_case() -> NeatGraphStore:
    print(car.CAR_RULES)
    store = NeatGraphStore.from_memory_store()

    for triple in car.TRIPLES:
        store.graph.add(triple)

    rules, _ = InferenceImporter.from_graph_store(store).to_rules()
    store.add_rules(rules)

    return store


class TestDMSLoader:
    def test_load_car_example(self, car_case: NeatGraphStore) -> None:
        loader = DMSLoader(
            car_case,
            car.CAR_MODEL,
            car.INSTANCE_SPACE,
            {
                car.CAR_MODEL.views[0].as_id(): "Car",
                car.CAR_MODEL.views[1].as_id(): "Manufacturer",
                car.CAR_MODEL.views[2].as_id(): "Color",
            },
        )

        loaded = loader.load(stop_on_exception=True)

        instances_source = {inst.external_id: inst.dump() for inst in car.INSTANCES}
        instances_target = {inst.external_id: inst.dump() for inst in loaded}

        assert dict(sorted(instances_source.items())) == dict(sorted(instances_target.items()))
