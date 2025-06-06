"""
Tor Browser Launcher
https://gitlab.torproject.org/tpo/applications/torbrowser-launcher/

Copyright (c) 2013-2021 Micah Lee <micah@micahflee.com>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
"""

import os
import sys
import platform
import subprocess
import pickle
import json
import re
import gettext
import gpg
import requests

SHARE = os.getenv("TBL_SHARE", sys.prefix + "/share") + "/torbrowser-launcher"

gettext.install("torbrowser-launcher")


class Common(object):
    def __init__(self, tbl_version):
        self.tbl_version = tbl_version

        # initialize the app
        self.architecture = "x86_64" if "64" in platform.architecture()[0] else "i686"
        self.default_mirror = "https://dist.torproject.org/"
        self.build_paths()
        self.torbrowser12_rename_old_tbb()
        for d in self.paths["dirs"]:
            self.mkdir(self.paths["dirs"][d])
        self.load_mirrors()
        self.load_settings()
        self.build_paths()
        self.mkdir(self.paths["download_dir"])
        self.mkdir(self.paths["tbb"]["dir"])
        self.init_gnupg()

    # get value of environment variable, if it is not set return the default value
    @staticmethod
    def get_env(var_name, default_value):
        value = os.getenv(var_name)
        if not value:
            value = default_value
        return value

    # build all relevant paths
    def build_paths(self, tbb_version=None):
        homedir = os.getenv("HOME")
        if not homedir:
            homedir = "/tmp/.torbrowser-" + os.getenv("USER")
            if not os.path.exists(homedir):
                try:
                    os.mkdir(homedir, 0o700)
                except:
                    self.set_gui(
                        "error", _("Error creating {0}").format(homedir), [], False
                    )

        tbb_config = "{0}/torbrowser".format(
            self.get_env("XDG_CONFIG_HOME", "{0}/.config".format(homedir))
        )
        tbb_cache = "{0}/torbrowser".format(
            self.get_env("XDG_CACHE_HOME", "{0}/.cache".format(homedir))
        )
        tbb_local = "{0}/torbrowser".format(
            self.get_env("XDG_DATA_HOME", "{0}/.local/share".format(homedir))
        )
        old_tbb_data = "{0}/.torbrowser".format(homedir)

        if tbb_version:
            # tarball filename
            if self.architecture == "x86_64":
                arch = "linux-x86_64"
            else:
                arch = "linux-i686"

            tarball_filename = "tor-browser-" + arch + "-" + tbb_version + ".tar.xz"

            # tarball
            self.paths["tarball_url"] = (
                "{0}torbrowser/" + tbb_version + "/" + tarball_filename
            )
            self.paths["tarball_file"] = tbb_cache + "/download/" + tarball_filename
            self.paths["tarball_filename"] = tarball_filename

            # sig
            self.paths["sig_url"] = (
                "{0}torbrowser/" + tbb_version + "/" + tarball_filename + ".asc"
            )
            self.paths["sig_file"] = (
                tbb_cache + "/download/" + tarball_filename + ".asc"
            )
            self.paths["sig_filename"] = tarball_filename + ".asc"
        else:
            self.paths = {
                "dirs": {
                    "config": tbb_config,
                    "cache": tbb_cache,
                    "local": tbb_local,
                },
                "old_data_dir": old_tbb_data,
                "tbl_bin": sys.argv[0],
                "icon_file": os.path.join(
                    os.path.dirname(SHARE), "icons/hicolor/128x128/apps/org.torproject.torbrowser-launcher.png"
                ),
                "torproject_pem": os.path.join(SHARE, "torproject.pem"),
                "signing_keys": {
                    "tor_browser_developers": os.path.join(
                        SHARE, "tor-browser-developers.asc"
                    ),
                    "wkd_tmp": os.path.join(tbb_cache, "torbrowser.gpg"),
                },
                "mirrors_txt": [
                    os.path.join(SHARE, "mirrors.txt"),
                    tbb_config + "/mirrors.txt",
                ],
                "download_dir": tbb_cache + "/download",
                "gnupg_homedir": tbb_local + "/gnupg_homedir",
                "settings_file": tbb_config + "/settings.json",
                "settings_file_pickle": tbb_config + "/settings",
                "version_check_url": "https://aus1.torproject.org/torbrowser/update_3/release/Linux_x86_64-gcc3/x/ALL",
                "version_check_file": tbb_cache + "/download/release.xml",
                "tbb": {
                    "changelog": tbb_local
                    + "/tbb/"
                    + self.architecture
                    + "/tor-browser/Browser/TorBrowser/Docs/ChangeLog.txt",
                    "dir": tbb_local + "/tbb/" + self.architecture,
                    "dir_tbb": tbb_local + "/tbb/" + self.architecture + "/tor-browser",
                    "start": tbb_local
                    + "/tbb/"
                    + self.architecture
                    + "/tor-browser/start-tor-browser.desktop",
                },
            }

        # Add the expected fingerprint for imported keys:
        tor_browser_developers_fingerprint = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
        self.fingerprints = {
            "tor_browser_developers": tor_browser_developers_fingerprint,
            "wkd_tmp": tor_browser_developers_fingerprint,
        }

    # Tor Browser 12.0 no longer has locales. If an old TBB folder exists with locals, rename it to just tor_browser
    def torbrowser12_rename_old_tbb(self):
        if not os.path.exists(self.paths["tbb"]["dir"]):
            return
        for filename in os.listdir(self.paths["tbb"]["dir"]):
            abs_filename = os.path.join(self.paths["tbb"]["dir"], filename)
            if filename.startswith("tor-browser_") and os.path.isdir(abs_filename):
                os.rename(abs_filename, self.paths["tbb"]["dir_tbb"])
                print(
                    _("Renamed {0} to {1}").format(
                        abs_filename, self.paths["tbb"]["dir_tbb"]
                    )
                )
                break

    # create a directory
    @staticmethod
    def mkdir(path):
        try:
            if not os.path.exists(path):
                os.makedirs(path, 0o700)
                return True
        except:
            print(_("Cannot create directory {0}").format(path))
            return False
        if not os.access(path, os.W_OK):
            print(_("{0} is not writable").format(path))
            return False
        return True

    # if gnupg_homedir isn't set up, set it up
    def init_gnupg(self):
        if not os.path.exists(self.paths["gnupg_homedir"]):
            print(_("Creating GnuPG homedir"), self.paths["gnupg_homedir"])
            self.mkdir(self.paths["gnupg_homedir"])
        self.import_keys()

    def proxies(self):
        # Use tor socks5 proxy, if enabled
        if self.settings["download_over_tor"]:
            socks5_address = "socks5h://{}".format(self.settings["tor_socks_address"])
            return {"https": socks5_address, "http": socks5_address}
        else:
            return None

    def refresh_keyring(self):
        print("Downloading latest Tor Browser signing key...")

        # Fetch key from wkd, as per https://support.torproject.org/tbb/how-to-verify-signature/
        # Sometimes GPG throws errors, so comment this out and download it directly
        # p = subprocess.Popen(
        #     [
        #         "gpg",
        #         "--status-fd",
        #         "2",
        #         "--homedir",
        #         self.paths["gnupg_homedir"],
        #         "--auto-key-locate",
        #         "nodefault,wkd",
        #         "--locate-keys",
        #         "torbrowser@torproject.org",
        #     ],
        #     stderr=subprocess.PIPE,
        # )
        # p.wait()

        # Download the key from WKD directly
        r = requests.get(
            "https://torproject.org/.well-known/openpgpkey/hu/kounek7zrdx745qydx6p59t9mqjpuhdf?l=torbrowser",
            proxies=self.proxies(),
        )
        if r.status_code != 200:
            print(f"Error fetching key, status code = {r.status_code}")
        else:
            with open(self.paths["signing_keys"]["wkd_tmp"], "wb") as f:
                f.write(r.content)

            if self.import_key_and_check_status("wkd_tmp"):
                print("Key imported successfully")
            else:
                print("Key failed to import")

    def import_key_and_check_status(self, key):
        """Import a GnuPG key and check that the operation was successful.
        :param str key: A string specifying the key's filepath from
            ``Common.paths``
        :rtype: bool
        :returns: ``True`` if the key is now within the keyring (or was
            previously and hasn't changed). ``False`` otherwise.
        """
        with gpg.Context() as c:
            c.set_engine_info(
                gpg.constants.protocol.OpenPGP, home_dir=self.paths["gnupg_homedir"]
            )

            impkey = self.paths["signing_keys"][key]
            try:
                c.op_import(gpg.Data(file=impkey))
            except:
                return False
            else:
                result = c.op_import_result()
                if result and self.fingerprints[key] in result.imports[0].fpr:
                    return True
                else:
                    return False

    # import gpg keys
    def import_keys(self):
        """Import all GnuPG keys.
        :rtype: bool
        :returns: ``True`` if all keys were successfully imported; ``False``
            otherwise.
        """
        keys = [
            "tor_browser_developers",
        ]
        all_imports_succeeded = True

        for key in keys:
            imported = self.import_key_and_check_status(key)
            if not imported:
                print(
                    _(
                        "Could not import key with fingerprint: %s."
                        % self.fingerprints[key]
                    )
                )
                all_imports_succeeded = False

        if not all_imports_succeeded:
            print(_("Not all keys were imported successfully!"))

        return all_imports_succeeded

    # load mirrors
    def load_mirrors(self):
        self.mirrors = []
        for srcfile in self.paths["mirrors_txt"]:
            if not os.path.exists(srcfile):
                continue
            for mirror in open(srcfile, "r").readlines():
                if mirror.strip() not in self.mirrors:
                    self.mirrors.append(mirror.strip())

    # load settings
    def load_settings(self):
        default_settings = {
            "tbl_version": self.tbl_version,
            "installed": False,
            "download_over_tor": False,
            "tor_socks_address": "127.0.0.1:9050",
            "mirror": self.default_mirror,
        }

        if os.path.isfile(self.paths["settings_file"]):
            settings = json.load(open(self.paths["settings_file"]))
            resave = False

            # detect installed
            settings["installed"] = os.path.isfile(self.paths["tbb"]["start"])

            # make sure settings file is up-to-date
            for setting in default_settings:
                if setting not in settings:
                    settings[setting] = default_settings[setting]
                    resave = True

            # make sure tor_socks_address doesn't start with 'tcp:'
            if settings["tor_socks_address"].startswith("tcp:"):
                settings["tor_socks_address"] = settings["tor_socks_address"][4:]
                resave = True

            # make sure the version is current
            if settings["tbl_version"] != self.tbl_version:
                settings["tbl_version"] = self.tbl_version
                resave = True

            self.settings = settings
            if resave:
                self.save_settings()

        # if settings file is still using old pickle format, convert to json
        elif os.path.isfile(self.paths["settings_file_pickle"]):
            self.settings = pickle.load(open(self.paths["settings_file_pickle"]))
            self.save_settings()
            os.remove(self.paths["settings_file_pickle"])
            self.load_settings()

        else:
            self.settings = default_settings
            self.save_settings()

    # save settings
    def save_settings(self):
        json.dump(self.settings, open(self.paths["settings_file"], "w"))
        return True
