import re
from dataclasses import dataclass
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class KnowledgeChunk:
    source: str
    text: str


DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _default_knowledge_dir():
    return Path(__file__).resolve().parent / "documents"


def _resolve_knowledge_dir(knowledge_dir):
    if knowledge_dir is None:
        return _default_knowledge_dir()
    path = Path(knowledge_dir)
    if path.is_absolute():
        return path
    # Relative Paths: Prefer As-Given Relative To CWD.
    if path.exists():
        return path
    # Fall Back To Locations Relative To This File / Repo Root So The
    # Retriever Works Regardless Of The Caller's Working Directory.
    here = Path(__file__).resolve().parent
    candidates = [
        here / path,
        here / path.name,
        here.parent.parent / path,
        _default_knowledge_dir(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Nothing Matched: Return The CWD-Relative Path So The Caller Gets
    # A Clear FileNotFoundError Mentioning What Was Requested.
    return path


_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)\-:]|[-*•])\s+\S")


def _split_paragraph_block(block: str):
    """Split One Blank-Line-Delimited Block Into Chunk Strings.

    List Blocks (Numbered/Bulleted) Are Split Per Item, Merging Wrapped
    Continuation Lines Into The Preceding Item. Plain Paragraphs Have
    Internal Single Newlines Collapsed To Spaces.
    """
    lines = [line.strip() for line in block.strip().splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []
    if not any(_LIST_ITEM_RE.match(line) for line in lines):
        return [" ".join(lines)]
    items: list[str] = []
    current = ""
    for line in lines:
        if _LIST_ITEM_RE.match(line):
            if current:
                items.append(current.strip())
            current = line
        else:
            # Continuation of the previous list item (wrapped line).
            current = f"{current} {line}".strip() if current else line
    if current:
        items.append(current.strip())
    return items


def chunk_text(text: str):
    """Split Raw Document Text Into Retrieval-Friendly Chunks."""
    blocks = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    for block in blocks:
        if block.strip():
            chunks.extend(_split_paragraph_block(block))
    return [c for c in (c.strip() for c in chunks) if c]


class KnowledgeRetriever:
    def __init__(
        self,
        knowledge_dir: str | Path | None = None,
        model_name: str = DEFAULT_MODEL,
        verbose: bool = False,
    ):
        self.knowledge_dir = _resolve_knowledge_dir(knowledge_dir)
        self.model_name = model_name
        self.verbose = verbose

        self.model = SentenceTransformer(model_name)

        self.chunks: list[KnowledgeChunk] = []
        self.embeddings = None

        self._load_documents()
        self._build_embeddings()

    def _load_documents(self):
        if not self.knowledge_dir.exists() or not self.knowledge_dir.is_dir():
            raise FileNotFoundError(
                f"Knowledge directory not found: {self.knowledge_dir}"
            )

        files = sorted(self.knowledge_dir.glob("*.txt"))
        if not files:
            raise ValueError(
                f"No .txt documents found in {self.knowledge_dir}"
            )

        for file_path in files:
            text = file_path.read_text(encoding="utf-8")
            for paragraph in chunk_text(text):
                self.chunks.append(
                    KnowledgeChunk(
                        source=file_path.name,
                        text=paragraph,
                    )
                )

        if not self.chunks:
            raise ValueError(
                f"No knowledge chunks loaded from {self.knowledge_dir}"
            )

    def _build_embeddings(self):
        texts = [chunk.text for chunk in self.chunks]

        self.embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        if self.verbose:
            print(f"Loaded {len(self.chunks)} Knowledge Chunks")
            print(f"Embedding Shape: {self.embeddings.shape}")

    def retrieve(self, query: str, top_k: int = 3):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if self.embeddings is None or not self.chunks:
            raise ValueError("Knowledge base is empty; cannot retrieve")

        top_k = min(top_k, len(self.chunks))

        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        scores = cosine_similarity(
            query_embedding,
            self.embeddings,
        )[0]

        ranked_indices = scores.argsort()[::-1][:top_k]

        results = []

        for index in ranked_indices:
            results.append(
                {
                    "source": self.chunks[index].source,
                    "text": self.chunks[index].text,
                    "score": float(scores[index]),
                }
            )

        return results
