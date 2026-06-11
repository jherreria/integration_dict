"""Dependency graph endpoints: full graph, component BFS, depth, deletion."""
import pytest

from .conftest import ADMIN, USER, create_integration


@pytest.fixture
def topology(client):
    """A->B->C flow, C->A (cycle), D integrated with B, E isolated."""
    ids = {}
    for name in ("A", "B", "C", "D", "E"):
        ids[name] = create_integration(client, name).json()["id"]
    # flow: A -> B -> C and C -> A (cycle)
    assert client.patch(
        f"/api/integrations/{ids['A']}", json={"downstream": [ids["B"]]}, headers=ADMIN
    ).status_code == 200
    assert client.patch(
        f"/api/integrations/{ids['B']}", json={"downstream": [ids["C"]]}, headers=ADMIN
    ).status_code == 200
    assert client.patch(
        f"/api/integrations/{ids['C']}", json={"downstream": [ids["A"]]}, headers=ADMIN
    ).status_code == 200
    # D integrated with B
    assert client.patch(
        f"/api/integrations/{ids['D']}", json={"integrated": [ids["B"]]}, headers=ADMIN
    ).status_code == 200
    return ids


def _flow_edges(body, ids):
    by_id = {v: k for k, v in ids.items()}
    return {
        (by_id[e["source"]], by_id[e["target"]])
        for e in body["edges"]
        if e["kind"] == "flow"
    }


def test_full_graph_nodes_edges_and_kinds(client, topology):
    body = client.get("/api/graph", headers=USER).json()
    assert {n["name"] for n in body["nodes"]} == {"A", "B", "C", "D", "E"}
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 4

    assert _flow_edges(body, topology) == {("A", "B"), ("B", "C"), ("C", "A")}
    integrated = [e for e in body["edges"] if e["kind"] == "integrated"]
    assert len(integrated) == 1
    assert {integrated[0]["source"], integrated[0]["target"]} == {
        topology["B"],
        topology["D"],
    }


def test_component_graph_excludes_isolated_and_marks_root(client, topology):
    body = client.get(f"/api/integrations/{topology['A']}/graph", headers=USER).json()
    names = {n["name"] for n in body["nodes"]}
    assert names == {"A", "B", "C", "D"}  # E is not connected; cycle terminated
    roots = [n["name"] for n in body["nodes"] if n["is_root"]]
    assert roots == ["A"]
    assert len(body["edges"]) == 4


def test_depth_one_returns_direct_neighbors_only(client, topology):
    body = client.get(
        f"/api/integrations/{topology['A']}/graph", params={"depth": 1}, headers=USER
    ).json()
    names = {n["name"] for n in body["nodes"]}
    # A -> B makes B a direct neighbor; C -> A makes C one. D is two hops away.
    assert names == {"A", "B", "C"}
    # only edges among returned nodes
    assert _flow_edges(body, topology) == {("A", "B"), ("B", "C"), ("C", "A")}
    assert all(e["kind"] == "flow" for e in body["edges"])


def test_deleting_node_removes_it_and_its_edges(client, topology):
    assert client.delete(f"/api/integrations/{topology['D']}", headers=ADMIN).status_code == 204

    body = client.get("/api/graph", headers=USER).json()
    assert {n["name"] for n in body["nodes"]} == {"A", "B", "C", "E"}
    assert len(body["edges"]) == 3
    assert all(e["kind"] == "flow" for e in body["edges"])

    # the link row to D no longer surfaces on B either
    b_detail = client.get(f"/api/integrations/{topology['B']}", headers=USER).json()
    assert b_detail["integrated"] == []
