import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Annotated

import typer
import supercut.ffmpeg as ffmpeg
import supercut.vlc as vlc
import pysubs2
import re
import random

app = typer.Typer()


def clone_subs(subs: pysubs2.SSAFile) -> pysubs2.SSAFile:
    return pysubs2.SSAFile.from_string(subs.to_string("ass"), "ass")


def should_replace(text: str) -> bool:
    return not text.startswith("{")


def make_replacer(words: list[str]) -> Callable[[str], str]:
    pat = re.compile(rf'\b({"|".join(map(re.escape, words))})\b', re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        return "_" * len(match.group(1))

    def replacer(text: str) -> str:
        if should_replace(text):
            return pat.sub(repl, text)
        return text

    return replacer


def drop_words(subs: pysubs2.SSAFile, words: list[str]) -> pysubs2.SSAFile:
    subs = clone_subs(subs)
    replacer = make_replacer(words)
    for event in subs.events:
        event.plaintext = replacer(event.text)

    return subs


def make_random_replacer(keep_ratio: float) -> Callable[[str], str]:
    pat = re.compile(r"\b(\\\w)?([\w']+)\b")

    def repl(match: re.Match[str]) -> str:
        newline = match.group(1) or ""
        word = match.group(2)
        if random.random() > keep_ratio:
            return newline + "_" * len(word)
        return newline + word

    def replacer(text: str) -> str:
        if should_replace(text):
            return pat.sub(repl, text)
        return text

    return replacer


def drop_random_words(subs: pysubs2.SSAFile, keep_ratio: float) -> pysubs2.SSAFile:
    subs = clone_subs(subs)
    replacer = make_random_replacer(keep_ratio)
    for event in subs.events:
        event.plaintext = replacer(event.text)
    return subs


def get_subs(video: Path) -> pysubs2.SSAFile:
    subs_path = video.with_suffix(".ssa")
    if subs_path.exists():
        return pysubs2.SSAFile.load(str(subs_path))

    subs = pysubs2.SSAFile.from_string(
        ffmpeg.extract_subs_by_language(video).decode("utf8")
    )
    subs.save(str(subs_path))

    return subs


def play_with_subs(video: Path, subs: pysubs2.SSAFile):
    with tempfile.TemporaryDirectory() as subs_dir:
        subs_path = Path(subs_dir) / "subs.ssa"
        subs.save(str(subs_path))
        cmd = [
            vlc.get_vlc(),
            "--fullscreen",
            "--sub-file",
            str(subs_path),
            str(video),
            "vlc://quit",
        ]
        subprocess.check_call(cmd)


@app.command()
def main(
    video: Annotated[
        Path,
        typer.Argument(help="The video to watch. Should contain embedded subtitles."),
    ],
    wordlist: Annotated[
        Optional[Path],
        typer.Option(help="File with words to hide. Each word on its own line."),
    ] = None,
    drop_rate: Annotated[
        Optional[int], typer.Option(help="Percentage of words to hide.")
    ] = None,
):
    subs = get_subs(video)

    if wordlist:
        words = wordlist.read_text().splitlines()
        subs = drop_words(subs, words)

    if drop_rate:
        subs = drop_random_words(subs, (100 - drop_rate) / 100)

    play_with_subs(video, subs)