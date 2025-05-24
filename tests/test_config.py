from docstub._config import Config


class Test_Config:
    def test_numpy_config(self):
        config = Config.from_toml(Config.NUMPY_PATH)
        assert len(config.types) > 0
        assert len(config.type_prefixes) > 0
        assert len(config.type_nicknames) > 0
