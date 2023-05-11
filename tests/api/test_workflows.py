import pytest
from cognite.client import CogniteClient
from starlette.testclient import TestClient

from cognite.neat.constants import EXAMPLE_WORKFLOWS
from cognite.neat.core.workflow import BaseWorkflow
from cognite.neat.core.workflow.model import WorkflowDefinition
from cognite.neat.explorer.data_classes.rest import RunWorkflowRequest
from tests.api.memory_cognite_client import MemoryClient


@pytest.fixture(scope="session")
def workflow_definitions() -> list[WorkflowDefinition]:
    definitions = []
    for example in EXAMPLE_WORKFLOWS.iterdir():
        definition = (example / "workflow.yaml").read_text()
        loaded = BaseWorkflow.deserialize_metadata(definition, "yaml")
        definitions.append(loaded)
    return definitions


@pytest.fixture(scope="session")
def workflow_names() -> list[str]:
    return [example.name for example in EXAMPLE_WORKFLOWS.iterdir()]


def test_load_example_workflows_loaded(workflow_names: list[str], fastapi_client: TestClient):
    # Act
    response = fastapi_client.get("/api/workflow/workflows")

    # Assert
    result = response.json()
    assert sorted(result["workflows"]) == sorted(workflow_names)


def test_load_rules(transformation_rules, fastapi_client: TestClient):
    response = fastapi_client.get("/api/rules")

    # Assert
    assert response.status_code == 200
    rules = response.json()
    assert len(transformation_rules.classes) == len(rules["classes"])
    assert len(transformation_rules.properties) == len(rules["properties"])


def test_run_default_workflow(cognite_client: CogniteClient, fastapi_client: TestClient, data_regression):
    response = fastapi_client.post(
        "/api/workflow/start",
        json=RunWorkflowRequest(name="default", sync=True, config={}, start_step="Not used").dict(),
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["error_text"] is None
    data = {}
    for resource_name in ["assets", "relationships", "labels"]:
        memory: MemoryClient = getattr(cognite_client, resource_name)
        data[resource_name] = memory.dump(ordered=True, exclude={"metadata.start_time", "metadata.update_time"})
    data_regression.check(data, basename="default_workflow")
