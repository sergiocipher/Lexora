import pytest
from app.consistent_hash import ConsistentHashRing

def test_consistent_hash_ring_initialization():
    nodes = ["redis-1", "redis-2", "redis-3"]
    ring = ConsistentHashRing(nodes=nodes, replicas=100)
    
    # 3 nodes * 100 replicas = 300 virtual nodes
    assert len(ring.ring) == 300
    assert len(ring.vnode_map) == 300
    
    # Ring should be sorted
    assert ring.ring == sorted(ring.ring)

def test_consistent_hash_ring_routing():
    nodes = ["redis-1", "redis-2", "redis-3"]
    ring = ConsistentHashRing(nodes=nodes, replicas=100)
    
    # Key routing should be deterministic
    node1 = ring.get_node("iphone")
    node2 = ring.get_node("iphone")
    assert node1 == node2
    
    # Prefix mapping should map to one of the configured nodes
    assert node1 in nodes
    
    # Different keys should map to their respective nodes
    node_a = ring.get_node("a")
    node_b = ring.get_node("b")
    node_c = ring.get_node("c")
    
    assert all(n in nodes for n in [node_a, node_b, node_c])

def test_node_addition_and_removal():
    nodes = ["redis-1", "redis-2"]
    ring = ConsistentHashRing(nodes=nodes, replicas=100)
    
    # Initially 200 virtual nodes
    assert len(ring.ring) == 200
    
    # Mapped node for prefix before adding redis-3
    key = "search_typeahead"
    initial_node = ring.get_node(key)
    
    # Add a new node
    ring.add_node("redis-3")
    assert len(ring.ring) == 300
    
    # Remove a node
    ring.remove_node("redis-2")
    assert len(ring.ring) == 200
    assert "redis-2" not in ring.vnode_map.values()
    
    # Key mapping should still be valid with remaining nodes
    new_node = ring.get_node(key)
    assert new_node in ["redis-1", "redis-3"]
