# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\resource\container.py
import zipfile, zlib, argparse, os, sys, logging
from lib.util.dict2obj import Dict2Obj
log = logging.getLogger("resource-container")

class ResourceContainer:

    def __init__(self):
        self.resource_path = self.get_resource_path()
        log.debug("Checking resources container: " + self.resource_path)
        self._exists = os.path.isfile(self.resource_path)
        if self._exists is True:
            self.pf = zipfile.ZipFile(self.resource_path)

    def dump(self):
        for info in self.pf.infolist():
            print("{0:s} - {1:d} bytes".format(info.filename, info.file_size))

    def get_resource_path(self):
        path = os.path.dirname(sys.executable)
        path = os.path.join(path, "resources.dat")
        if os.path.isfile(path):
            return path
        path = os.path.dirname(sys.argv[0])
        path = os.path.join(path, "resources.dat")
        return path

    def exists(self):
        return self._exists

    def load(self, resource_path):
        if resource_path.find("/") == 0:
            resource_path = resource_path[1[:None]]
        log.debug("Loading {0:s} from resources container.".format(resource_path))
        try:
            info = self.pf.getinfo(resource_path)
            if info is None:
                return
        except KeyError as ke:
            try:
                log.error("Could not find {0:s} in the resources container".format(resource_path))
                return
            finally:
                ke = None
                del ke

        content = self.pf.read(resource_path)
        if content is None:
            return
        return Dict2Obj({'content':content, 
         'size':info.file_size})


class ResourceContainerCLI:

    def __init__(self):
        self.parser = argparse.ArgumentParser(description="Resource packaging")
        self.parser.add_argument("--resources_path", help="The path of the resources root folder to be packaged.", required=True)
        self.parser.add_argument("--package", help="The path and file name of the output file containing packaged resources.", required=True)
        self.args = self.parser.parse_args()

    def pack_resources(self, package, path):
        pf = zipfile.ZipFile(package, mode="w")
        try:
            for dir_name, sub_dirs, files in os.walk(path, topdown=False):
                for file in files:
                    full_path = os.path.join(dir_name, file)
                    resource_path = full_path.replace(path + os.sep, "")
                    resource_path = resource_path.replace(os.sep, "/")
                    print("Packing {0:s}".format(resource_path))
                    pf.write(full_path, arcname=resource_path)

        finally:
            pf.close()

    def start(self):
        package = self.args.package
        resources_path = self.args.resources_path.replace("/", os.sep)
        print(resources_path)
        if os.path.isdir(resources_path):
            self.pack_resources(package, resources_path)
        else:
            relative_resources_path = os.path.join(os.path.dirname(sys.argv[0]), resources_path)
            print(relative_resources_path)
            if os.path.isdir(relative_resources_path):
                self.pack_resources(package, resources_path)
            else:
                print("{0:s} does not appear to be a valid folder/directory.".format(resources_path))


if __name__ == "__main__":
    cli = ResourceContainerCLI()
    cli.start()

# okay decompiling pyz_out/lib/util/resource/container.pyc
