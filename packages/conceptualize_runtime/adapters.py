"""Adapters from supported source formats to generic ContextUnits."""

from __future__ import annotations

from typing import Protocol

from .context import ContextUnit


class ContextSourceAdapter(Protocol):
    source_type: str

    def adapt(self, source: object) -> list[ContextUnit]: ...


class RepositoryAdapter:
    """View the existing repository index through the generic context boundary."""

    source_type = "repository_file"

    def adapt(self, files: dict[str, dict], graph=None) -> list[ContextUnit]:
        units = []
        for path, record in sorted(files.items()):
            relations = []
            if graph is not None and path in graph:
                relations.extend(
                    {"kind": data.get("kind", "related"), "source": a, "target": b}
                    for a, b, data in graph.edges(path, data=True)
                )
                relations.extend(
                    {"kind": data.get("kind", "related"), "source": a, "target": b}
                    for a, b, data in graph.in_edges(path, data=True)
                )
            units.append(ContextUnit(
                id=f"repository:{path}",
                source_type=self.source_type,
                source_id=path,
                content=record.get("content", ""),
                content_hash=record["hash"] if record.get("hash") else "",
                relationships=relations,
                metadata={
                    "path": path,
                    "language": record.get("language"),
                    "symbols": record.get("symbols", []),
                },
            ))
            for symbol in record.get("symbols", []):
                signature = symbol.get("signature") or symbol["name"]
                units.append(
                    ContextUnit(
                        id=f"repository:{path}::symbol:{symbol['name']}:{symbol['start_line']}",
                        source_type="code_symbol",
                        source_id=f"{path}::{symbol['name']}:{symbol['start_line']}",
                        parent_id=f"repository:{path}",
                        content=signature,
                        relationships=[{"kind": "declared_in", "target": f"repository:{path}"}],
                        metadata={"path": path, **symbol},
                    )
                )
        return units


class ConversationAdapter:
    """Convert structured conversations into ordered, linked message units."""

    source_type = "message"

    def ingest(self, payload: dict) -> list[ContextUnit]:
        if not isinstance(payload, dict) or not isinstance(payload.get("conversations"), list):
            raise ValueError("conversation payload must include a conversations list")
        units = []
        for conversation in payload["conversations"]:
            if not isinstance(conversation, dict) or not conversation.get("id"):
                raise ValueError("each conversation requires an id")
            conversation_id = str(conversation["id"])
            title = conversation.get("title")
            messages = conversation.get("messages", [])
            if not isinstance(messages, list):
                raise ValueError("conversation messages must be a list")
            prior_id = None
            seen_ids = set()
            first_timestamp = None
            last_timestamp = None
            for order, message in enumerate(messages):
                if not isinstance(message, dict) or not message.get("id"):
                    raise ValueError("each message requires an id")
                message_id = str(message["id"])
                if message_id in seen_ids:
                    raise ValueError(f"duplicate message id in conversation: {message_id}")
                seen_ids.add(message_id)
                role = message.get("role")
                content = message.get("content")
                if role not in {"user", "assistant", "system", "tool", "developer"}:
                    raise ValueError(f"unsupported message role: {role}")
                if not isinstance(content, str):
                    raise ValueError("message content must be a string")
                first_timestamp = first_timestamp or message.get("timestamp")
                last_timestamp = message.get("timestamp") or last_timestamp
                unit_id = f"conversation:{conversation_id}/message:{message_id}"
                parent_message_id = message.get("parent_id") or prior_id
                relationships = [
                    {"kind": "member_of", "target": f"conversation:{conversation_id}"}
                ]
                if prior_id:
                    relationships.append(
                        {
                            "kind": "follows",
                            "source": f"conversation:{conversation_id}/message:{prior_id}",
                            "target": unit_id,
                        }
                    )
                if parent_message_id:
                    relationships.append(
                        {
                            "kind": "reply_to",
                            "source": unit_id,
                            "target": f"conversation:{conversation_id}/message:{parent_message_id}",
                        }
                    )
                attachments = message.get("attachments", [])
                if attachments is None:
                    attachments = []
                if not isinstance(attachments, list):
                    raise ValueError("message attachments must be a list")
                units.append(
                    ContextUnit(
                        id=unit_id,
                        source_type=self.source_type,
                        source_id=message_id,
                        parent_id=(
                            f"conversation:{conversation_id}/message:{parent_message_id}"
                            if parent_message_id
                            else None
                        ),
                        content=content,
                        created_at=message.get("timestamp"),
                        metadata={
                            "conversation_id": conversation_id,
                            "title": title,
                            "role": role,
                            "order": order,
                            "timestamp": message.get("timestamp"),
                            "attachments": attachments,
                            "references": message.get("references", []),
                            "explicit_metadata": message.get("metadata", {}),
                        },
                        relationships=relationships,
                    )
                )
                prior_id = message_id
            conversation_unit_id = f"conversation:{conversation_id}"
            units.append(
                ContextUnit(
                    id=conversation_unit_id,
                    source_type="conversation",
                    source_id=conversation_id,
                    content=title or "",
                    created_at=first_timestamp,
                    updated_at=last_timestamp or first_timestamp,
                    relationships=[
                        {
                            "kind": "contains",
                            "source": conversation_unit_id,
                            "target": f"conversation:{conversation_id}/message:{message['id']}",
                        }
                        for message in messages
                    ],
                    metadata={
                        "conversation_id": conversation_id,
                        "title": title,
                        "explicit_metadata": conversation.get("metadata", {}),
                    },
                )
            )
        return units

    def adapt(self, source: object) -> list[ContextUnit]:
        if not isinstance(source, dict):
            raise ValueError("conversation source must be a structured dictionary")
        return self.ingest(source)

    def export(self, units: list[ContextUnit]) -> dict:
        conversations = {}
        for unit in units:
            if unit.source_type == "conversation":
                conversation_id = unit.metadata["conversation_id"]
                conversation = conversations.setdefault(
                    conversation_id,
                    {"id": conversation_id, "title": None, "metadata": {}, "messages": []},
                )
                conversation["title"] = unit.metadata.get("title")
                conversation["metadata"] = unit.metadata.get("explicit_metadata", {})
                continue
            if unit.source_type != self.source_type:
                continue
            conversation_id = unit.metadata["conversation_id"]
            conversation = conversations.setdefault(
                conversation_id,
                {"id": conversation_id, "title": unit.metadata.get("title"), "messages": []},
            )
            conversation["messages"].append(
                {
                    "id": unit.source_id,
                    "role": unit.metadata["role"],
                    "timestamp": unit.metadata.get("timestamp"),
                    "order": unit.metadata["order"],
                    "content": unit.content,
                    "attachments": unit.metadata.get("attachments", []),
                    "references": unit.metadata.get("references", []),
                    "metadata": unit.metadata.get("explicit_metadata", {}),
                    "parent_id": unit.parent_id.rsplit("/message:", 1)[-1]
                    if unit.parent_id
                    else None,
                }
            )
        return {
            "conversations": [
                {**conversation, "messages": sorted(conversation["messages"], key=lambda m: m["order"])}
                for conversation in conversations.values()
            ]
        }
