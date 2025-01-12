from typing import Dict, Set, Optional, List, Any


class ComfyStatusLog:
    def __init__(
        self,
        prompt_id: str,
        node: Optional[str] = None,
        value: Optional[int] = 1,
        max: Optional[int] = 1,
        status: Optional[str] = None,
        nodes: Optional[List[str]] = None,
    ):
        self.prompt_id = prompt_id
        self.node = node
        self.value = value
        self.max = max
        self.status = status
        self.nodes = nodes

    def from_comfy_message(self, message_data: Dict[str, Any], prompt_id: str):
        self.prompt_id = prompt_id
        self.node = message_data.get("node", None)
        self.status = message_data.get("status", None)
        self.max = message_data.get("max", 1)
        self.value = message_data.get("value", 1)
        self.nodes = message_data.get("nodes", [])
        return self


class ComfyJobProgress:
    def __init__(self, prompt: Dict[str, any]):
        self.status_logs: List[ComfyStatusLog] = []
        self.prompt = prompt
        self.visited_nodes: Set[str] = set()
        self.current_node: Optional[ComfyStatusLog] = None
        self.total_nodes: Set[str] = set(self.prompt.keys())
        self.last_percentage: float = 0

    def remove_cached_nodes_from_total_nodes(self, status_log: ComfyStatusLog):
        if status_log.nodes:
            self.total_nodes -= set(status_log.nodes)

    def add_status_log(self, status_log: ComfyStatusLog):
        self.remove_cached_nodes_from_total_nodes(status_log)
        self.status_logs.append(status_log)
        if status_log.node is not None:
            self.current_node = status_log
        if (
            self.current_node
            and self.current_node.node
            and self.current_node.node in self.total_nodes
        ):
            self.visited_nodes.add(self.current_node.node)

    def get_status_logs(self) -> List[ComfyStatusLog]:
        return self.status_logs

    def get_current_node_percentage(self) -> float:
        node_total_percentage = 100 / len(self.total_nodes)
        value = self.current_node.value if self.current_node else 1
        max = self.current_node.max if self.current_node else 1
        node_percentage = value / max
        return min(node_percentage * node_total_percentage, 100)

    def get_percentage(self) -> float:
        current_node_percentage = self.get_current_node_percentage()
        has_max = self.current_node and self.current_node.max != 1
        has_value = self.current_node and self.current_node.value
        node_has_progress = has_max and has_value
        last_percentage = (
            (len(self.visited_nodes) - (0 if node_has_progress else 1))
            / len(self.total_nodes)
        ) * 100
        new_percentage = last_percentage + current_node_percentage
        self.last_percentage = min(max(new_percentage, self.last_percentage), 100)
        return round(self.last_percentage, 2)
