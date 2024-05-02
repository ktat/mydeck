import unittest

from mydeck import Config, MyDeck, VirtualDeck, DeckInput, DeckOutput
import logging


class MyDecksTest(unittest.TestCase):
    logging.basicConfig(level=logging.ERROR)

    def setUp(self):
        input = DeckInput({})
        output = DeckOutput({})
        deck = VirtualDeck({
            "key_count": 15,
            "columns": 5,
            "has_touchscreen": False,
            "dial_count": 0,
            "id": "vdeck1",
            "serial_number": "vdeck1",
        }, input, output)
        self.mydeck = MyDeck({"deck": deck}, 3000)

    def test_unify_app_config_same_app_same_setting_same_key(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        self.assertFalse(config.unify_app_config(
            "conf_key", "page1", 1, new_app_config))
        self.assertEqual(config._config_content_origin,
                         {"apps": [existing_config]})

    def test_unify_app_config_same_app_same_setting_different_page(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page2": 2
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        self.assertTrue(config.unify_app_config(
            "conf_key", "page2", 2, new_app_config))
        self.assertEqual(config._config_content_origin, {
            "apps": [
                {
                    "app": "my_app",
                    "option": {
                        "conf_key": {
                            "page1": 1,
                            "page2": 2,
                        }
                    }
                }
            ]
        })

    def test_unify_app_config_same_app_same_setting_different_key(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 2
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}

        self.assertTrue(config.unify_app_config(
            "conf_key", "page1", 2, new_app_config))

        self.assertEqual(config._config_content_origin,
                         {"apps": [new_app_config]})

    def test_unify_app_config_same_app_different_setting_same_key(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "hoge": 1,
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "hoge": 2,
                "conf_key": {
                    "page1": 1
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}

        self.assertTrue(config.unify_app_config(
            "conf_key", "page1", 1, new_app_config))
        self.assertEqual(config._config_content_origin,
                         {"apps": [new_app_config]})

    def test_different_app_already_exists(self):
        existing_config = {
            "app": "other_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        self.assertTrue(config.unify_app_config(
            "conf_key", "page1", 1, new_app_config))
        self.assertEqual(config._config_content_origin,
                         {"apps": [new_app_config]})

    def test_no_app_config_exists(self):
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": []}
        self.assertTrue(config.unify_app_config(
            "conf_key", "page1", 1, new_app_config))
        self.assertEqual(config._config_content_origin,
                         {"apps": [new_app_config]})

    def test_new_app_config_added(self):
        existing_config = {
            "app": "other_app",
            "option": {
                "conf_key": {
                    "page1": 1
                }
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "conf_key": {
                    "page2": 1
                }
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        self.assertTrue(config.unify_app_config(
            "conf_key", "page2", 1, new_app_config))

        self.assertEqual(config._config_content_origin, {
                         "apps": [existing_config, new_app_config]})

    def test_unify_touchscreen_app_config_same_app_same_page(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "page": ["page1"]
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "page": ["page1"]
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        assert config.unify_touchscreen_app_config(
            "page1", new_app_config) == False
        assert config._config_content_origin == {"apps": [existing_config]}

    def test_unify_touchscreen_app_config_same_app_different_page(self):
        existing_config = {
            "app": "my_app",
            "option": {
                "page": ["page1"]
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "page": ["page2"]
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        assert config.unify_touchscreen_app_config(
            "page2", new_app_config) == True
        assert config._config_content_origin == {
            "apps": [
                {
                    "app": "my_app",
                    "option": {
                        "page": ["page1", "page2"]
                    }
                }
            ]
        }

    def test_unify_touchscreen_app_config_different_app_same_page(self):
        existing_config = {
            "app": "other_app",
            "option": {
                "page": ["page1"]
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "page": ["page1"]
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        assert config.unify_touchscreen_app_config(
            "page1", new_app_config) == True
        assert config._config_content_origin == {"apps": [new_app_config]}

    def test_unify_touchscreen_app_config_no_app_config_exists(self):
        new_app_config = {
            "app": "my_app",
            "option": {
                "page": ["page1"]
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": []}
        assert config.unify_touchscreen_app_config(
            "page1", new_app_config) == True
        assert config._config_content_origin == {"apps": [new_app_config]}

    def test_unify_touchscreen_app_config_new_app_config_added(self):
        existing_config = {
            "app": "other_app",
            "option": {
                "page": ["page1"]
            }
        }
        new_app_config = {
            "app": "my_app",
            "option": {
                "page": ["page2"]
            }
        }
        config = Config(self.mydeck, "")
        config._config_content_origin = {"apps": [existing_config]}
        assert config.unify_touchscreen_app_config(
            "page2", new_app_config) == True
        assert config._config_content_origin == {
            "apps": [existing_config, new_app_config]}


if __name__ == "__main__":
    unittest.main()
