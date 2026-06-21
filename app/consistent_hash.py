import hashlib
from bisect import bisect_right
from typing import List, Dict, Optional

class ConsistentHashRing:
    """
    Consistent Hash Ring mapping prefixes/keys to a set of Redis nodes.
    Uses virtual nodes to ensure even distribution and minimize key movement.
    """
    def __init__(self, nodes: Optional[List[str]] = None, replicas: int = 100):
        self.replicas = replicas
        self.ring: List[int] = []  # Sorted list of virtual node hashes
        self.vnode_map: Dict[int, str] = {}  # Map from vnode hash to physical node string (e.g. 'localhost:6379')
        
        if nodes:
            for node in nodes:
                self.add_node(node)
                
    def _hash(self, key: str) -> int:
        """Hash key using MD5 and return an integer representation (128-bit ring)."""
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
        
    def add_node(self, node: str) -> None:
        """Add a physical node to the ring with virtual replicas."""
        for i in range(self.replicas):
            vnode_key = f"{node}#vnode_{i}"
            vnode_hash = self._hash(vnode_key)
            if vnode_hash not in self.vnode_map:
                self.ring.append(vnode_hash)
                self.vnode_map[vnode_hash] = node
        self.ring.sort()
        
    def remove_node(self, node: str) -> None:
        """Remove a physical node and its virtual replicas from the ring."""
        for i in range(self.replicas):
            vnode_key = f"{node}#vnode_{i}"
            vnode_hash = self._hash(vnode_key)
            if vnode_hash in self.vnode_map:
                self.ring.remove(vnode_hash)
                del self.vnode_map[vnode_hash]
        self.ring.sort()
        
    def get_node(self, key: str) -> Optional[str]:
        """Get the physical node that the key maps to."""
        if not self.ring:
            return None
            
        key_hash = self._hash(key)
        # Find the first virtual node with a hash >= key_hash
        idx = bisect_right(self.ring, key_hash)
        
        # Wrap around to the first node if key_hash is greater than all hashes on the ring
        if idx == len(self.ring):
            idx = 0
            
        return self.vnode_map[self.ring[idx]]
