# processor.py
#
# Copyright 2022 mirkobrombin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundationat version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import uuid
import shutil
import logging
import tempfile
import subprocess
from glob import glob


logger = logging.getLogger("Installer::Processor")


class Processor:

    @staticmethod
    def gen_swap_size():
        """
        Reference: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/7/html/storage_administration_guide/ch-swapspace#doc-wrapper
        """
        mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        mem = mem / (1024.0 ** 3)
        if mem <= 2:
            return int(mem * 3 * 1024)
        elif mem > 2 and mem <= 8:
            return int(mem * 2 * 1024)
        elif mem > 8 and mem <= 64:
            return int(mem * 1.5 * 1024)
        else:
            return 4096

    @staticmethod
    def gen_install_script(log_path, pre_run, post_run, finals):
        logger.info("processing the following final data: %s", finals)

        #manifest_remove = "/cdrom/casper/filesystem.manifest-remove"
        #if not os.path.exists(manifest_remove):
        manifest_remove = "/tmp/filesystem.manifest-remove"
        with open(manifest_remove, "w") as f:
            f.write("vanilla-installer\n")
            f.write("gparted\n")

        arguments = [
            "sudo", "distinst",
            "-s", "'/cdrom/casper/filesystem.squashfs'",
            "-r", f"'{manifest_remove}'",
            "-h", "'vanilla'",
        ]

        is_almost_supported = shutil.which("almost")

        # post install variables
        device_block = ""
        tz_region = ""
        tz_zone = ""

        for final in finals:
            for key, value in final.items():
                if key == "users":
                    arguments = ["echo", f"'{value['password']}'", "|"] + arguments
                    arguments += ["--username", f"'{value['username']}'"]
                    arguments += ["--realname", f"'{value['fullname']}'"]
                    arguments += ["--profile_icon", "'/usr/share/pixmaps/faces/yellow-rose.jpg'"]
                elif key == "timezone":
                    arguments += ["--tz", "'{}/{}'".format(value["region"], value["zone"])]
                    tz_region = value["region"]
                    tz_zone = value["zone"]
                elif key == "language":
                    arguments += ["-l", f"'{value}'"]
                elif key == "keyboard":
                    arguments += ["-k", f"'{value}'"]
                elif key == "disk":
                    if "auto" in value:
                        arguments += ["-b", f"'{value['auto']['disk']}'"]
                        arguments += ["-t", "'{}:gpt'".format(value["auto"]["disk"])]
                        arguments += ["-n", "'{}:primary:start:1024M:fat32:mount=/boot/efi:flags=esp'".format(value["auto"]["disk"])]
                        arguments += ["-n", "'{}:primary:1024M:2048M:ext4:mount=/boot'".format(value["auto"]["disk"])]
                        arguments += ["-n", "'{}:primary:2048M:22528M:btrfs:mount=/'".format(value["auto"]["disk"])]
                        arguments += ["-n", "'{}:primary:22528M:43008M:btrfs:mount=/'".format(value["auto"]["disk"])]
                        arguments += ["-n", "'{}:primary:43008M:end:btrfs:mount=/home'".format(value["auto"]["disk"])]
                        #  arguments += ["-n", "'{}:primary:-{}M:end:swap'".format(value["auto"]["disk"], Processor.gen_swap_size())]
                        device_block = value["auto"]["disk"]
                    else:
                        raise NotImplementedError("Manual partitioning is not yet supported. Yes it will be soon.")
                        for partition, values in value.items():
                            if partition == "disk":
                                arguments += ["-b", f"'{values}'"]
                                arguments += ["-t", "'{}:gpt'".format(values)]
                                continue
                            if values["mp"] == "/":
                                arguments += ["-n", "'{}:primary:start:{}M:btrfs:mount=/'".format(partition, values["size"])]
                            elif values["mp"] == "/boot/efi":
                                arguments += ["-n", "'{}:primary:start:512M:fat32:mount=/boot/efi:flags=esp'".format(partition)]
                            elif values["mp"] == "swap":
                                arguments += ["-n", "'{}:primary:{}M:end:swap'".format(partition, values["size"])]
                            else:
                                arguments += ["-n", "'{}:primary:{}M:end:{}:mount={}'".format(partition, values["size"], values["fs"], values["mp"])]
        
        # generating a temporary file to store the distinst command and
        # arguments parsed from the final data
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("#!/bin/sh\n")
            f.write("# This file was created by the Vanilla Installer.\n")
            f.write("# Do not edit this file manually!\n\n")

            if is_almost_supported:
                f.write("almost enter rw\n")

            f.write("set -e -x\n\n")

            if "VANILLA_FAKE" in os.environ:
                logger.info("VANILLA_FAKE is set, skipping the installation process.")
                f.write("echo 'VANILLA_FAKE is set, skipping the installation process.'\n")
                f.write("echo 'Printing the configuration instead:'\n")
                f.write("echo '----------------------------------'\n")
                f.write('echo "{}"\n'.format(finals))
                f.write("echo '----------------------------------'\n")
                f.write("sleep 5\n")
                f.write("exit 1\n")

            if "VANILLA_SKIP_INSTALL" not in os.environ:
                for arg in arguments:
                    f.write(arg + " ")

            if "VANILLA_SKIP_POSTINSTALL" not in os.environ:
                f.write("\n")
                f.write("echo 'Starting the post-installation process ...'\n")
                f.write("sudo abroot-adapter {} {} {}"
                        .format(device_block, tz_region, tz_zone))

            f.flush()
            f.close()

            # setting the file executable
            os.chmod(f.name, 0o755)
            
            return f.name
