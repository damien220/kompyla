from pathlib import Path


class KBLayout:
    """Defines and manages the directory structure of a single knowledge base."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.raw = self.root / "raw"
        self.wiki = self.root / "wiki"
        self.index_dir = self.root / "index"
        self.tools = self.root / "tools"
        self.outputs = self.root / "outputs"
        self.schema_file = self.index_dir / "schema.yaml"
        self.index_file = self.index_dir / "index.md"
        self.meta_db = self.index_dir / "meta.db"
        self.feedback_db = self.index_dir / "feedback.db"
        self.kb_config = self.root / "kompyla.yaml"

    def create(self) -> None:
        for d in (self.raw, self.wiki, self.index_dir, self.tools, self.outputs):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_cwd(cls) -> "KBLayout":
        return cls(Path.cwd())
