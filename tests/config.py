from pathlib import Path

TEST_FOLDER = Path(__file__).resolve().parent
ROOT = TEST_FOLDER.parent
PACKAGE_DIRECTORY = ROOT / "cognite" / "neat"

DATA_FOLDER = TEST_FOLDER / "data"
PYPROJECT_TOML = ROOT / "pyproject.toml"

# Example rule files
TNT_TRANSFORMATION_RULES = PACKAGE_DIRECTORY / "rules" / "examples" / "Rules-Nordic44-to-TNT.xlsx"
SIMPLE_TRANSFORMATION_RULES = PACKAGE_DIRECTORY / "rules" / "examples" / "sheet2cdf-transformation-rules.xlsx"

# Example graph files
NORDIC44_KNOWLEDGE_GRAPH = PACKAGE_DIRECTORY / "graph" / "examples" / "Knowledge-Graph-Nordic44.xml"

GRAPH_CAPTURING_SHEET = DATA_FOLDER / "sheet2cdf-graph-capturing.xlsx"
WIND_ONTOLOGY = DATA_FOLDER / "wind-energy.owl"
