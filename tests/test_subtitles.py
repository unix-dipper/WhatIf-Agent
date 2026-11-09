from whatif.subtitles import cues_for_scene, format_srt_time, split_text


def test_srt_format():
    assert format_srt_time(3661.234) == "01:01:01,234"


def test_text_is_split_and_timed():
    chunks = split_text("One. Two. Three.", 20)
    assert len(chunks) == 3
    cues = cues_for_scene("One. Two. Three.", 2.0, 3.0, 20)
    assert cues[0].start == 2.0
    assert cues[-1].end == 5.0
    assert all(cues[i].end <= cues[i + 1].start for i in range(len(cues) - 1))
