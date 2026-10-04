"""Where the server looks for the training pipeline: the same code must work from a checkout and from inside the Docker image."""
from pathlib import PurePosixPath

from app.inference import root_candidates


class Posix:
    """A path whose resolve() is itself, so the Docker layout can be checked on any operating system."""

    def __init__(self, text):
        self.p = PurePosixPath(text)

    def resolve(self):
        return self.p

    def __getattr__(self, name):
        return getattr(self.p, name)


def test_from_a_checkout_the_repository_root_is_found():
    found = root_candidates(Posix("/work/prescribble/apps/api/app/inference.py"))
    assert str(found[0]).replace("\\", "/") == "/work/prescribble" and str(found[-1]).replace("\\", "/") == "/app"


def test_inside_the_docker_image_the_file_is_too_shallow_for_a_fourth_parent_and_that_must_not_crash():
    found = root_candidates(Posix("/app/app/inference.py"))                   # this raised IndexError and made the image crash on start
    assert [str(p).replace("\\", "/") for p in found] == ["/app"]
