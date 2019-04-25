"""
This component provides support for Battery Level.
For more details about this component, please refer to the documentation at
https://home-assistant.io/components/ham/
"""
import sys
import logging

from homeassistant.const import (EVENT_HOMEASSISTANT_START)
from homeassistant.helpers.event import track_time_interval
from time import gmtime, strftime

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.zwave import DOMAIN as ZWAVE_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from .const import *

DEPENDENCIES = [BINARY_SENSOR_DOMAIN, SENSOR_DOMAIN, SWITCH_DOMAIN, LOCK_DOMAIN, LIGHT_DOMAIN, ZWAVE_DOMAIN,
                CLIMATE_DOMAIN, NOTIFY_DOMAIN]

_LOGGER = logging.getLogger(__name__)


class BatteryLevelData:
    """The Class for handling the data retrieval."""

    def __init__(self, hass, scan_interval, notify_data):
        """Initialize the data object."""
        _LOGGER.debug("BatteryLevelData initialization")

        self._notify_data = notify_data
        self._entity_ids = []
        self._low_battery_level = []

        self._hass = hass
        self._was_initialized = False

        def bl_refresh(event_time):
            """Call Battery Level to refresh information."""
            _LOGGER.debug(f'Updating Battery Level component, at {event_time}')
            self.update()

        def bl_notify(event_time):
            """Call Battery Level to refresh information."""
            _LOGGER.debug(f'Notify Battery Level component, at {event_time}')
            self.notify()

        self._bl_refresh = bl_refresh
        self._bl_notify = bl_notify

        # register service
        hass.services.register(DOMAIN, 'update', bl_refresh)
        hass.services.register(DOMAIN, 'send_report', bl_notify)

        # register scan interval for Battery Level
        track_time_interval(hass, bl_refresh, scan_interval)

        hass.bus.listen_once(EVENT_HOMEASSISTANT_START, bl_refresh)

        self._was_initialized = True

    def was_initialized(self):
        return self._was_initialized

    def create_persistent_notification(self, message):
        self._hass.components.persistent_notification.create(
            message,
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID)

    def load_domain_entities(self, domain):
        entity_ids = self._hass.states.entity_ids(domain)

        for entity_id in entity_ids:
            try:
                state = self._hass.states.get(entity_id)

                if ATTR_FRIENDLY_NAME in state.attributes:
                    entity_friendly_name = state.attributes[ATTR_FRIENDLY_NAME]
                else:
                    entity_friendly_name: state.name

                if ATTR_BATTERY_LEVEL in state.attributes:
                    battery_level_entity_id = f'{entity_id}_battery_level'.replace(domain, SENSOR_DOMAIN)
                    battery_level_state = state.attributes[ATTR_BATTERY_LEVEL]

                    if str(battery_level_state).replace(".", "").isdigit():
                        battery_level_friendly_name = f'{entity_friendly_name} Battery Level'
                        battery_level_attributes = {
                            ATTR_FRIENDLY_NAME: battery_level_friendly_name,
                            ATTR_UNIT_OF_MEASUREMENT: '%'
                        }

                        should_update = True

                        log_message = f'Sensor {battery_level_friendly_name} of entity_id: {entity_friendly_name}'
                        if battery_level_entity_id in self._entity_ids:
                            current_state = self._hass.states.get(battery_level_entity_id).state

                            if str(current_state) == str(battery_level_state):
                                _LOGGER.debug(f'{log_message} was not updated')
                                should_update = False
                            else:
                                _LOGGER.info(f'{log_message} updated from {current_state} to {battery_level_state}')
                        else:
                            _LOGGER.info(f'{log_message} created, Level: {battery_level_state}')
                            self._entity_ids.append(battery_level_entity_id)

                        battery_level_value = float(battery_level_state)
                        threshold = float(self._notify_data[CONF_THRESHOLD])

                        if self._notify_data is not None and battery_level_value <= threshold:
                            self._low_battery_level.append(battery_level_entity_id)

                        if should_update:
                            self._hass.states.set(battery_level_entity_id, battery_level_state, battery_level_attributes)
                    else:
                        _LOGGER.info(
                            f'Entity {entity_id} contains battery_level attribute, Invalid state: {battery_level_state}')
            except Exception as ex:
                exc_type, exc_obj, tb = sys.exc_info()
                line_number = tb.tb_lineno

                _LOGGER.error(f'Failed to create battery level sensor for {entity_id}, Error: {str(ex)}, Line: {line_number}')

    def notify(self):
        if self._notify_data is not None:

            threshold = self._notify_data[CONF_THRESHOLD]
            notify_entity_id = self._notify_data[CONF_NOTIFY_ENTITY_ID]

            title = f'*Low Battery Report (=<{threshold}%)*'
            message = "None of the component is below threshold"

            _LOGGER.info(f'Notify data: {self._notify_data}')

            low_battery_level_state = len(self._low_battery_level)

            if low_battery_level_state > 0:
                message_items = []
                for entity_id in self._low_battery_level:
                    item = self._hass.states.get(entity_id)

                    if item is not None:
                        name = item.attributes[ATTR_FRIENDLY_NAME].replace(DEFAULT_NAME, '')

                        message_items.append(f' - {name} ({item.state}%)')

                message = '\r\n'.join([str(x) for x in message_items])

            entity_id = notify_entity_id.replace(f'{NOTIFY_DOMAIN}.', '')

            data = {
                'title': title,
                'message': message
            }

            _LOGGER.info(f'Sending notification via {entity_id}: {data}')

            self._hass.services.call(NOTIFY_DOMAIN, entity_id, data, False)

    def update_low_battery_summary(self):
        low_battery_level_entity_id = f'{SENSOR_DOMAIN}.low_battery_level'
        low_battery_level_attributes = {
            ATTR_FRIENDLY_NAME: "Low Battery Level",
            ATTR_UNIT_OF_MEASUREMENT: 'Components'
        }

        if len(self._low_battery_level) > 0:
            for entity_id in self._low_battery_level:
                item = self._hass.states.get(entity_id)
                item_name = item.attributes[ATTR_FRIENDLY_NAME].replace(DEFAULT_NAME, '')
                item_state = f'{item.state}%'

                low_battery_level_attributes[item_name] = item_state

        low_battery_level_state = len(self._low_battery_level)

        self._hass.states.set(low_battery_level_entity_id, low_battery_level_state, low_battery_level_attributes)

    def update(self):
        try:
            _LOGGER.debug("update - Start")

            domains = [SENSOR_DOMAIN, BINARY_SENSOR_DOMAIN, LIGHT_DOMAIN, SWITCH_DOMAIN, ZWAVE_DOMAIN, CLIMATE_DOMAIN,
                       LOCK_DOMAIN]

            self._low_battery_level = []

            for domain in domains:
                _LOGGER.info(f'Updating components of {domain} domain')

                self.load_domain_entities(domain)

            self.update_low_battery_summary()

            time_now = strftime("%H:%M", gmtime())

            if self._notify_data is not None and CONF_NOTIFY_WHEN in self._notify_data and time_now == \
                    self._notify_data[CONF_NOTIFY_WHEN]:
                self.notify()

            _LOGGER.debug("update - Completed")
        except Exception as ex:
            _LOGGER.error(f'Error while updating {DOMAIN}, exception: {str(ex)}')
