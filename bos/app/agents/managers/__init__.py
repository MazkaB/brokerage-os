"""Manager agents.

Managers receive the CEO's plan and orchestrate the appropriate worker
sub-graph. They use Gemini to decide which workers to invoke and in what
order, then merge the worker outputs.
"""
from .operations_manager import operations_manager_node
from .compliance_manager import compliance_manager_node
from .portfolio_manager import portfolio_manager_node

MANAGER_REGISTRY = {
    "operations": operations_manager_node,
    "compliance": compliance_manager_node,
    "portfolio": portfolio_manager_node,
}

__all__ = ["operations_manager_node", "compliance_manager_node",
           "portfolio_manager_node", "MANAGER_REGISTRY"]
