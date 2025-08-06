"""
Defines the core data structures for the application using Pydantic.

This module provides centralized, validated models that ensure data consistency
across different components like the orchestrator, memory manager, tool agent,
and response parser. Using these models prevents common data-related errors
and makes the application's data flow explicit and self-documenting.
"""

import uuid
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional, Union


class ParsedAgentResponse(BaseModel):
    """
    A structured representation of the parsed agent response.
    
    This model is the output of the response_parser and the primary input for
    the orchestrator's rendering and execution logic. It cleanly separates
    the natural language part of a model's output from its machine-readable command.
    """
    # The natural language portion of the model's response, if any exists.
    prose: Optional[str] = None
    # The structured command the agent wishes to execute.
    command: Optional['ToolCommand'] = None
    # A pre-calculated flag for rendering efficiency, indicating if the prose
    # is empty or contains only a timestamp.
    is_prose_empty: bool = True


class ToolCommand(BaseModel):
    """
    Represents a command issued by the agent to be executed by the tool agent.
    This model validates the structure of the agent's JSON output.
    """

    # The specific name of the tool to be executed, e.g., 'read_file', 'list_directory'.
    action: str = Field(..., description="The name of the tool to be executed.")
    # A flexible dictionary of parameters for the specified tool. For example,
    # for 'create_file', this would contain {'filename': 'x.py', 'content': 'print("hello")'}.
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="A dictionary of parameters for the specified tool.",
    )
    # Optional prose or reasoning from the agent, attached to the command for context.
    # This is used by the renderer to display the agent's "thoughts" before a tool runs.
    attachment: Optional[str] = Field(
        default=None,
        description="Optional prose from the agent, attached to the command.",
    )


class ToolResult(BaseModel):
    """
    Represents a standardized result returned after a tool is executed.
    This ensures that the orchestrator receives a predictable data structure
    from the tool_agent, regardless of which tool was run.
    """

    # Indicates whether the tool execution succeeded or failed. This is crucial
    # for the orchestrator's control flow.
    status: Literal["success", "error"] = Field(..., description="Indicates whether the tool execution was successful.")
    # A human-readable message describing the outcome, intended for UI logging.
    message: str = Field(..., description="A human-readable message describing the outcome.")
    # Optional content returned by the tool, such as file content, a list of files,
    # or the output of a script.
    content: Optional[Any] = Field(
        default=None,
        description="Optional content returned by the tool.",
    )


class MemoryRecord(BaseModel):
    """
    Represents a single record stored in the ChromaDB vector store.
    This standardizes data across the memory manager, summarizer, and database
    inspector, ensuring all components work with the same data schema.
    """

    # The primary key for the record in the database.
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the memory record.",
    )
    # The type of memory, used to partition data for different recall purposes.
    type: Literal["turn", "segment_summary", "code_artifact"] = Field("turn", description="The type of memory this record represents.")
    # For conversational turns, indicates whether the user or the model was speaking.
    role: Optional[Literal["user", "model"]] = Field(default=None, description="The role associated with a conversational turn.")
    # The UNIX timestamp of when the event occurred, used for chronological sorting.
    timestamp: float = Field(..., description="The UNIX timestamp of the event.")
    # The primary text content of the record. This is the field that gets
    # converted into a vector for similarity searches.
    document: str = Field(
        ...,
        description="The primary text content of the record, used for vectorization.",
    )
    # A concise summary of the document, part of a tiered memory system for efficiency.
    summary: Optional[str] = Field(default=None, description="A concise summary of the document, if available.")
    # The full prompt (including RAG context) that led to this turn. Essential
    # for auditing and debugging the agent's reasoning process.
    augmented_prompt: Optional[str] = Field(
        default=None,
        description="The full prompt (including RAG context) that led to this turn.",
    )
    # The original, unsummarized content. For turns, this is the same as 'document'
    # initially but can be used to preserve original data through summarization cycles.
    raw_content: Optional[str] = Field(
        default=None,
        description="The original, unsummarized content.",
    )
    # The ID of the summary "chapter" this turn belongs to, used for organizing
    # conversational history into larger narrative blocks.
    segment_id: Optional[uuid.UUID] = Field(
        default=None,
        description="The ID of the 'chapter' summary this turn belongs to.",
    )
    # For code artifacts, the name of the file this content belongs to.
    filename: Optional[str] = Field(default=None, description="For code artifacts, the name of the file.")

# This is necessary for Pydantic to resolve the forward reference of 'ToolCommand'
# within the ParsedAgentResponse model.
ParsedAgentResponse.model_rebuild()
