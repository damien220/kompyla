from pydantic import BaseModel, Field


class PageType(BaseModel):
    name: str
    description: str
    required_sections: list[str] = Field(default_factory=list)


class EntityCategory(BaseModel):
    name: str
    description: str
    examples: list[str] = Field(default_factory=list)


class RelationshipType(BaseModel):
    name: str
    from_type: str
    to_type: str
    description: str


class DomainSchema(BaseModel):
    domain: str
    description: str
    page_types: list[PageType]
    entity_categories: list[EntityCategory]
    relationship_types: list[RelationshipType]
    seed_queries: list[str]
