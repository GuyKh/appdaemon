import requests
import inspect

import appdaemon.appapi as appapi
import appdaemon.utils as utils

#
# Define an entities class as a descriptor to enable read only access of HASS state
#

class Entities:

    def __get__(self, instance, owner):
        stateattrs = utils.StateAttrs(owner.get_state(owner))
        return stateattrs


class Hass(appapi.AppDaemon):
    #
    # Internal
    #

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, global_vars):

        super(Hass, self).__init__(ad, name, logger, error, args, config, global_vars)

        self.namespace = "hass"
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.global_vars = global_vars
        self.config = config

    def hass_check(func):
        def func_wrapper(*args, **kwargs):
            self = args[0]
            if not self.ad.get_plugin(self._get_namespace(kwargs)).reading_messages:
                utils.log(self._logger, "WARNING", "Attempt to call Home Assistant while disconnected: {}".format(func))
                return lambda *args: None
            else:
                return func(*args, **kwargs)

        return (func_wrapper)

    def _sub_stack(self, msg):
        # If msg is a data structure of some type, don't sub
        if type(msg) is str:
            stack = inspect.stack()
            if msg.find("__module__") != -1:
                msg = msg.replace("__module__", stack[2][1])
            if msg.find("__line__") != -1:
                msg = msg.replace("__line__", str(stack[2][2]))
            if msg.find("__function__") != -1:
                msg = msg.replace("__function__", stack[2][3])
        return msg

    def set_namespace(self, namespace):
        self.namespace = namespace

    def _get_namespace(self, **kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self.namespace

        return namespace


    #
    # Listen state stub here as super class doesn't know the namespace
    #

    def listen_state(self, cb, entity=None, **kwargs):
        namespace = self._get_namespace(kwargs)
        return super(Hass, self).listen_state(namespace, cb, entity, **kwargs)

    #
    # Likewise with get and set state
    #

    def get_state(self, entity=None, **kwargs):
        namespace = self._get_namespace(kwargs)
        return super(Hass, self).get_state(namespace, entity, **kwargs)

    def set_state(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        self._check_entity(namespace, entity_id)
        utils.log(
            self._logger, "DEBUG",
            "set_state: {}, {}".format(entity_id, kwargs)
        )

        if entity_id in self.get_state():
            new_state = self.get_state()[entity_id]
        else:
            # Its a new state entry
            new_state = {}
            new_state["attributes"] = {}

        if "state" in kwargs:
            new_state["state"] = kwargs["state"]

        if "attributes" in kwargs:
            new_state["attributes"].update(kwargs["attributes"])

        # Send update to plugin

        self.ad.get_plugin(namespace).set_state(entity_id, new_state)

        # Update AppDaemon's copy

        self.ad.set_state(namespace, entity_id, new_state)

        return new_state

    def entity_exists(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        return self.ad.entity_exists(namespace, entity_id)
    #
    # Utility
    #


    def split_entity(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        return entity_id.split(".")

    def split_device_list(self, list_):
        return list_.split(",")

    def log(self, msg, level="INFO"):
        msg = self._sub_stack(msg)
        utils.log(self._logger, level, msg, self.name)

    def error(self, msg, level="WARNING"):
        msg = self._sub_stack(msg)
        utils.log(self._error, level, msg, self.name)

    #
    #
    #

    def friendly_name(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        state = self.get_state()
        if entity_id in state:
            if "friendly_name" in state[entity_id]["attributes"]:
                return state[entity_id]["attributes"]["friendly_name"]
            else:
                return entity_id
        return None

    #
    # Device Trackers
    #

    def get_trackers(self, **kwargs):
        return (key for key, value in self.get_state("device_tracker", kwargs).items())

    def get_tracker_details(self, **kwargs):
        return self.get_state("device_tracker", kwargs)

    def get_tracker_state(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        return self.get_state(entity_id)

    def anyone_home(self, **kwargs):
        state = self.get_state(kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] == "home":
                    return True
        return False

    def everyone_home(self, **kwargs):
        state = self.get_state(kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] != "home":
                    return False
        return True

    def noone_home(self, **kwargs):
        state = self.get_state(kwargs)
        for entity_id in state.keys():
            thisdevice, thisentity = entity_id.split(".")
            if thisdevice == "device_tracker":
                if state[entity_id]["state"] == "home":
                    return False
        return True

    #
    # Helper functions for services
    #

    @hass_check
    def turn_on(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
        self.call_service("homeassistant/turn_on", **rargs)

    @hass_check
    def turn_off(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
        
        device, entity = self.split_entity(entity_id)
        if device == "scene":
            self.call_service("homeassistant/turn_on", **rargs)
        else:
            self.call_service("homeassistant/turn_off", **rargs)

    @hass_check
    def toggle(self, entity_id, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id

        self.call_service("homeassistant/toggle", **rargs)

    @hass_check
    def select_value(self, entity_id, value, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id, "value": value}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            rargs["value"] = value
        self.call_service("input_slider/select_value", **rargs)

    @hass_check
    def select_option(self, entity_id, option, **kwargs):
        self._check_entity(self._get_namespace(kwargs), entity_id)
        if kwargs == {}:
            rargs = {"entity_id": entity_id, "option": option}
        else:
            rargs = kwargs
            rargs["entity_id"] = entity_id
            rargs["option"] = option
        self.call_service("input_select/select_option", **rargs)

    @hass_check
    def notify(self, message, **kwargs):
        kwargs["message"] = message
        if "name" in kwargs:
            service = "notify/{}".format(kwargs["name"])
        else:
            service = "notify/notify"

        self.call_service(service, **kwargs)

    @hass_check
    def persistent_notification(self, message, title=None, id=None):
        kwargs = {}
        kwargs["message"] = message
        if title is not None:
            kwargs["title"] = title
        if id is not None:
            kwargs["notification_id"] = id
        self.call_service("persistent_notification/create", **kwargs)


    #
    # Event
    #

    @hass_check
    def fire_event(self, event, **kwargs):
        utils.log(self._logger, "DEBUG",
                  "fire_event: {}, {}".format(event, kwargs))
        config = self.ad.get_plugin(self._get_namespace(kwargs)).config
        if "ha_key" in config and config["ha_key"] != "":
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}
        apiurl = "{}/api/events/{}".format(config["ha_url"], event)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=conf.certpath
        )
        r.raise_for_status()
        return r.json()

    #
    # Service
    #
    @staticmethod
    def _check_service(service):
        if service.find("/") == -1:
            raise ValueError("Invalid Service Name: {}".format(service))

    @hass_check
    def call_service(self, service, **kwargs):
        self._check_service(service)
        d, s = service.split("/")
        utils.log(
            self._logger, "DEBUG",
            "call_service: {}/{}, {}".format(d, s, kwargs)
        )

        config = self.ad.get_plugin(self._get_namespace(kwargs)).config

        if "ha_key" in config and config["ha_key"] != "":
            headers = {'x-ha-access': config["ha_key"]}
        else:
            headers = {}
        apiurl = "{}/api/services/{}/{}".format(config["ha_key"], d, s)
        r = requests.post(
            apiurl, headers=headers, json=kwargs, verify=conf.certpath
        )
        r.raise_for_status()
        return r.json()
