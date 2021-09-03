import json
from json import JSONDecodeError
import os
import copy
import warnings


class Configuration:

    def __init__(self, path=r"./configure.json") -> None:
        self._path = path
        self._config = {
            "SAMPLING_FREQUENCY": 2.4e9,
            "RELATIVE_TIMING": True,
            "PHASE_ALIGNMENT": "Trigger",
            "TRIGGER_DELAY": 0
        }
        self._supported = self._config.keys()
        try:
            self.load_config()
        except (FileNotFoundError, AssertionError, JSONDecodeError):
            self.dump_config()

    def load_config(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError("./configure.json does not exist")
        with open(self._path, "r") as f:
            loaded_config = json.load(f)
            self._validate(loaded_config)
            self._config = loaded_config

    def dump_config(self):
        with open(self._path, "w+") as f:
            f.writelines(json.dumps(self._config, indent=4))

    def update(self, key, value):
        if key not in self._supported:
            raise Exception(f"{key} is not a supported configuration")
        test_config = copy.deepcopy(self._config)
        test_config[key] = value
        try:
            self._validate(test_config)
            self._config = test_config
            self.dump_config()
        except AssertionError:
            warnings.warn("The updated configuration is not valid!")

    def retrieve(self, key):
        if key not in self._supported:
            raise Exception(f"{key} is not a supported configuration")
        return self._config[key]

    def set_path(self, path):
        # check for permission
        if os.access(os.path.split(path)[0], os.W_OK):
            self._path = path
        else:
            warnings.warn(
                "Do not have access to the directory, configuration path has not been modified")

    @staticmethod
    def _validate(config):
        assert(config["PHASE_ALIGNMENT"] in ("Trigger", "Zero"))
        assert(isinstance(config["TRIGGER_DELAY"], int))
        assert(isinstance(config["RELATIVE_TIMING"], bool))
        assert(isinstance(config["SAMPLING_FREQUENCY"], float) or
               isinstance(config["SAMPLING_FREQUENCY"], int))
        assert(config["SAMPLING_FREQUENCY"] > 0)
