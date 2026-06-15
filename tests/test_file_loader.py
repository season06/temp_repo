from rag_adapter.loaders.file_loader import FileLoader


async def test_file_loader_reads_single_file(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>hi</p>", encoding="utf-8")

    docs = await FileLoader(loader_name="html").load(str(f))

    assert len(docs) == 1
    assert docs[0].text == "<p>hi</p>"
    assert docs[0].id == str(f)
    assert docs[0].source_ref.loader == "html"
    assert docs[0].source_ref.location == str(f)


async def test_file_loader_reads_directory_recursively(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("B", encoding="utf-8")

    docs = await FileLoader().load(str(tmp_path))

    texts = sorted(d.text for d in docs)
    assert texts == ["A", "B"]
