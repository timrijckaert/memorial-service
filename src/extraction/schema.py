# src/extraction/schema.py
"""Shared constants and JSON schema for the extraction pipeline."""

__all__ = ["PERSON_SCHEMA", "MLX_TEXT_MODEL", "MLX_VISION_MODEL"]

MLX_TEXT_MODEL = "mlx-community/gemma-3-4b-it-4bit"
MLX_VISION_MODEL = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "person": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "nullable": True},
                "last_name": {"type": "string", "nullable": True},
                "birth_date": {"type": "string", "nullable": True},
                "birth_place": {"type": "string", "nullable": True},
                "death_date": {"type": "string", "nullable": True},
                "death_place": {"type": "string", "nullable": True},
                "age_at_death": {"type": "integer", "nullable": True},
                "spouses": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouses",
            ],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["person", "notes"],
}
