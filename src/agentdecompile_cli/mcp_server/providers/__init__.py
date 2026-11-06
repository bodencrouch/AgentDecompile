"""MCP tool providers – Python implementations of MCP tools.

Each provider registers HANDLERS (normalized tool name → method) and list_tools();
``PROVIDER_CLASSES`` is the single ordered enrollment list consumed by
ToolProviderManager, which dispatches tools/call to the selected provider.
"""

from .decompiler import DecompilerToolProvider
from .functions import FunctionToolProvider
from .symbols import SymbolToolProvider
from .memory import MemoryToolProvider
from .data import DataToolProvider
from .strings import StringToolProvider
from .structures import StructureToolProvider
from .enums import EnumToolProvider
from .xrefs import CrossReferencesToolProvider
from .comments import CommentToolProvider
from .conflict_resolution import ConflictResolutionToolProvider
from .bookmarks import BookmarkToolProvider
from .project import ProjectToolProvider
from .callgraph import CallGraphToolProvider
from .getfunction import GetFunctionToolProvider
from .import_export import ImportExportToolProvider
from .dataflow import DataFlowToolProvider
from .constants import ConstantSearchToolProvider
from .vtable import VtableToolProvider
from .script import ScriptToolProvider
from .search_everything import SearchEverythingToolProvider
from .suggestions import SuggestionToolProvider
from .datatypes import DataTypeToolProvider
from .dissect import GetFunctionAioToolProvider
from .batch_analysis import BatchAnalysisToolProvider
from .decomp_match import DecompMatchToolProvider
from .prompts import PromptToolProvider
from .static_analysis import StaticAnalysisToolProvider
from .recovery import RecoveryToolProvider
from .workflow import WorkflowToolProvider
from .context_substrate import ContextSubstrateToolProvider

PROVIDER_CLASSES = (
    BookmarkToolProvider,
    BatchAnalysisToolProvider,
    DecompMatchToolProvider,
    CallGraphToolProvider,
    CommentToolProvider,
    ConflictResolutionToolProvider,
    ConstantSearchToolProvider,
    ContextSubstrateToolProvider,
    CrossReferencesToolProvider,
    DataFlowToolProvider,
    DataToolProvider,
    DataTypeToolProvider,
    DecompilerToolProvider,
    EnumToolProvider,
    GetFunctionAioToolProvider,
    FunctionToolProvider,
    GetFunctionToolProvider,
    ImportExportToolProvider,
    MemoryToolProvider,
    ProjectToolProvider,
    PromptToolProvider,
    ScriptToolProvider,
    StaticAnalysisToolProvider,
    RecoveryToolProvider,
    WorkflowToolProvider,
    SearchEverythingToolProvider,
    StringToolProvider,
    StructureToolProvider,
    SuggestionToolProvider,
    SymbolToolProvider,
    VtableToolProvider,
)

__all__ = [provider.__name__ for provider in PROVIDER_CLASSES]
