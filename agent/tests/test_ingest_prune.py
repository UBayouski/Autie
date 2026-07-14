"""Unit tests for the --prune sweep (no credentials or network needed).

prune() deletes production data, so the selection rule and the batching are
worth pinning down.
"""

from dataclasses import dataclass, field

from ingestion.ingest import _DELETE_BATCH, prune


@dataclass
class FakeDoc:
    id: str

    @property
    def reference(self) -> str:
        return self.id


@dataclass
class FakeCollection:
    ids: list[str]

    def select(self, _fields):
        return self

    def stream(self):
        return [FakeDoc(i) for i in self.ids]


@dataclass
class FakeBatch:
    deleted: list[str] = field(default_factory=list)
    committed: bool = False

    def delete(self, reference):
        self.deleted.append(reference)

    def commit(self):
        self.committed = True


@dataclass
class FakeDb:
    batches: list[FakeBatch] = field(default_factory=list)

    def batch(self) -> FakeBatch:
        self.batches.append(FakeBatch())
        return self.batches[-1]


def test_prune_deletes_only_ids_not_written_this_run():
    db = FakeDb()
    collection = FakeCollection(ids=["keep1", "stale1", "keep2", "stale2"])

    removed = prune(db, collection, keep_ids={"keep1", "keep2"})

    assert removed == 2
    deleted = [d for b in db.batches for d in b.deleted]
    assert sorted(deleted) == ["stale1", "stale2"]


def test_prune_keeps_everything_when_all_ids_were_written():
    db = FakeDb()
    collection = FakeCollection(ids=["a", "b"])

    removed = prune(db, collection, keep_ids={"a", "b"})

    assert removed == 0
    assert all(not b.deleted for b in db.batches)


def test_prune_respects_firestore_batch_limit():
    total = _DELETE_BATCH * 2 + 5
    db = FakeDb()
    collection = FakeCollection(ids=[f"stale{i}" for i in range(total)])

    removed = prune(db, collection, keep_ids=set())

    assert removed == total
    assert all(len(b.deleted) <= 500 for b in db.batches)
    assert all(b.committed for b in db.batches)
    assert sum(len(b.deleted) for b in db.batches) == total
