from rdflib import XSD, Literal

from cognite.neat.graph.extractors.graph_sheet_to_graph import sheet2triples
from cognite.neat.graph.stores import NeatGraphStore
from cognite.neat.utils.utils import remove_namespace


def test_sheet2graph(simple_rules, graph_capturing_sheet):
    graph_store = NeatGraphStore(prefixes=simple_rules.prefixes, namespace=simple_rules.metadata.namespace)
    graph_store.init_graph(base_prefix=simple_rules.metadata.prefix)

    graph_store.add_triples(sheet2triples(graph_capturing_sheet, simple_rules))

    count_dict = {
        remove_namespace(res[0]): int(res[1])
        for res in list(
            graph_store.graph.query(
                "SELECT ?class (count(?s) as ?instances ) WHERE { ?s a ?class . } "
                "group by ?class order by DESC(?instances)"
            )
        )
    }

    assert next(iter(graph_store.graph.query("Select ?o WHERE { neat:Country-1 neat:TSO ?o }")))[0] == Literal(
        "Statnett", datatype=XSD.string
    )
    assert count_dict == {"PriceArea": 2, "CountryGroup": 1, "Country": 1, "PriceAreaConnection": 1}
