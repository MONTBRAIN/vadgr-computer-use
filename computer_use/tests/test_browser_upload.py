# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""upload path translation — the WSL boundary (four-platforms, non-negotiable).

``DOM.setFileInputFiles`` resolves each path in the *browser* process's OS. On
WSL, Chrome is Windows Chrome over the bridge, so a cua-side WSL path is
unreadable to it; cua rewrites each ``files[]`` entry to a Chrome-OS path BEFORE
the op crosses the wire. Native Chrome shares cua's filesystem → paths pass
through unchanged. WSL is the only boundary that must be proven here.
"""

from computer_use.browser.upload import translate_upload_paths


class TestNativePlatformsPassThrough:
    def test_linux_paths_unchanged(self):
        files = ["/home/u/cv.pdf", "/tmp/photo.png"]
        assert translate_upload_paths(files, platform="linux") == files

    def test_windows_paths_unchanged(self):
        files = ["C:\\Users\\me\\cv.pdf"]
        assert translate_upload_paths(files, platform="win32") == files

    def test_darwin_paths_unchanged(self):
        files = ["/Users/me/cv.pdf"]
        assert translate_upload_paths(files, platform="darwin") == files


class TestWslBoundary:
    def test_mnt_c_maps_to_windows_drive_path(self):
        out = translate_upload_paths(
            ["/mnt/c/Users/me/cv.pdf"], platform="wsl", distro="Ubuntu"
        )
        assert out == ["C:\\Users\\me\\cv.pdf"]

    def test_mnt_other_drive(self):
        out = translate_upload_paths(
            ["/mnt/d/data/file.txt"], platform="wsl", distro="Ubuntu"
        )
        assert out == ["D:\\data\\file.txt"]

    def test_rootfs_path_maps_to_wsl_unc(self):
        out = translate_upload_paths(
            ["/home/u/cv.pdf"], platform="wsl", distro="Ubuntu"
        )
        assert out == ["\\\\wsl.localhost\\Ubuntu\\home\\u\\cv.pdf"]

    def test_mixed_paths(self):
        out = translate_upload_paths(
            ["/mnt/c/a.pdf", "/home/u/b.pdf"], platform="wsl", distro="Deb"
        )
        assert out == ["C:\\a.pdf", "\\\\wsl.localhost\\Deb\\home\\u\\b.pdf"]

    def test_empty_list(self):
        assert translate_upload_paths([], platform="wsl", distro="Ubuntu") == []
