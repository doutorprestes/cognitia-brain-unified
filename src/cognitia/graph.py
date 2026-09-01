"""Módulo para gerenciar o Grafo de Conhecimento (Knowledge Graph)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from cognitia_brain.config import Config

logger = logging.getLogger(__name__)

class GraphDB:
    def __init__(self, config: Config) -> None:
        self.path = config.acervo_dir.parent / ".chromadb" / "knowledge_graph.json"
        self.graph = nx.Graph()
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.graph = nx.node_link_graph(data)
                logger.info(f"Grafo carregado: {self.graph.number_of_nodes()} nós.")
            except Exception as e:
                logger.error(f"Erro ao carregar grafo: {e}")
                self.graph = nx.Graph()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = nx.node_link_data(self.graph)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Erro ao salvar grafo: {e}")

    def add_entity(self, name: str, type_: str, doc_id: str = None) -> None:
        if not name:
            return
        # Normalizar nome simples
        name = name.strip().lower()
        if not self.graph.has_node(name):
            self.graph.add_node(name, type=type_)
        if doc_id:
            self.graph.nodes[name]["doc_id"] = doc_id

    def add_relation(self, source: str, target: str, relation: str) -> None:
        if not source or not target:
            return
        source = source.strip().lower()
        target = target.strip().lower()
        
        # Garante que nós existam mesmo se esquecidos na lista de entidades
        if not self.graph.has_node(source):
            self.graph.add_node(source, type="Unknown")
        if not self.graph.has_node(target):
            self.graph.add_node(target, type="Unknown")
            
        if not self.graph.has_edge(source, target):
            self.graph.add_edge(source, target, relations=[relation])
        else:
            rels = self.graph[source][target].setdefault("relations", [])
            if relation not in rels:
                rels.append(relation)

    def merge_data(self, entities: list[dict], relations: list[dict]) -> list[str]:
        """
        Mescla as novas entidades e relações no grafo.
        Retorna uma lista de nós (nomes) antigamente isolados ou pertencentes a 
        contextos antigos que agora se conectaram a coisas novas.
        """
        old_nodes = set(self.graph.nodes)
        intersections = set()

        for ent in entities:
            self.add_entity(ent.get("nome", ""), ent.get("tipo", ""), ent.get("doc_id"))
            
        for rel in relations:
            src = rel.get("fonte", "").strip().lower()
            tgt = rel.get("alvo", "").strip().lower()
            tipo = rel.get("tipo", "")
            
            if src and tgt:
                self.add_relation(src, tgt, tipo)
                # Verifica interseções: se um nó era velho e conectou com um novo
                if src in old_nodes and tgt not in old_nodes:
                    intersections.add(src)
                elif tgt in old_nodes and src not in old_nodes:
                    intersections.add(tgt)
                    
        self.save()
        return list(intersections)

    def get_entity_relations(self, entity_name: str) -> List[Dict]:
        """Get all relations for an entity."""
        entity_name = entity_name.strip().lower()
        relations = []

        if not self.graph.has_node(entity_name):
            return relations

        for neighbor in self.graph.neighbors(entity_name):
            edge_data = self.graph[entity_name][neighbor]
            relations.append({
                "source": entity_name,
                "target": neighbor,
                "relations": edge_data.get("relations", []),
                "target_type": self.graph.nodes[neighbor].get("type", "Unknown")
            })

        return relations

    def find_paths(self, source: str, target: str, max_length: int = 3) -> List[List[str]]:
        """Find paths between two entities."""
        source = source.strip().lower()
        target = target.strip().lower()

        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return []

        try:
            paths = list(nx.all_simple_paths(self.graph, source, target, cutoff=max_length))
            return paths[:10]  # Limit to 10 paths
        except nx.NetworkXError:
            return []

    def get_entity_neighbors(self, entity_name: str, depth: int = 1) -> Set[str]:
        """Get neighbors of an entity up to a certain depth."""
        entity_name = entity_name.strip().lower()
        if not self.graph.has_node(entity_name):
            return set()

        neighbors = set()
        current_level = {entity_name}

        for _ in range(depth):
            next_level = set()
            for node in current_level:
                for neighbor in self.graph.neighbors(node):
                    if neighbor not in neighbors:
                        next_level.add(neighbor)
                        neighbors.add(neighbor)
            current_level = next_level

        return neighbors

    def get_communities(self) -> List[Set[str]]:
        """Detect communities in the graph."""
        try:
            communities = list(nx.community.greedy_modularity_communities(self.graph))
            return communities
        except Exception:
            return []

    def get_central_entities(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get most central entities by degree centrality."""
        centrality = nx.degree_centrality(self.graph)
        sorted_entities = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return sorted_entities[:top_n]

    def get_entity_types(self) -> Dict[str, int]:
        """Get count of entities by type."""
        type_counts = defaultdict(int)
        for node, data in self.graph.nodes(data=True):
            entity_type = data.get("type", "Unknown")
            type_counts[entity_type] += 1
        return dict(type_counts)

    def get_relation_types(self) -> Dict[str, int]:
        """Get count of relations by type."""
        relation_counts = defaultdict(int)
        for u, v, data in self.graph.edges(data=True):
            for relation in data.get("relations", []):
                relation_counts[relation] += 1
        return dict(relation_counts)

    def search_entities(self, query: str, n_results: int = 10) -> List[Dict]:
        """Search entities by name."""
        query = query.strip().lower()
        results = []

        for node, data in self.graph.nodes(data=True):
            if query in node:
                results.append({
                    "name": node,
                    "type": data.get("type", "Unknown"),
                    "degree": self.graph.degree(node)
                })

        # Sort by degree (most connected first)
        results.sort(key=lambda x: x["degree"], reverse=True)
        return results[:n_results]

    def get_subgraph(self, entity_name: str, depth: int = 2) -> nx.Graph:
        """Get a subgraph around an entity."""
        entity_name = entity_name.strip().lower()
        if not self.graph.has_node(entity_name):
            return nx.Graph()

        neighbors = self.get_entity_neighbors(entity_name, depth)
        neighbors.add(entity_name)
        return self.graph.subgraph(neighbors).copy()

    def get_stats(self) -> Dict:
        """Get graph statistics."""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "components": nx.number_connected_components(self.graph),
            "entity_types": self.get_entity_types(),
            "relation_types": self.get_relation_types()
        }
