# app/hydro_system/rules/pump_rule.py

from .base_rule import ActuatorRule
from app.core.logging_config import get_logger
from app.hydro_system.helpers.comparision_helper import (
    safe_lt,
)

logger = get_logger(__name__)


class PumpRule(ActuatorRule):

    actuator_type = "pump"

    def should_activate(
        self,
        sensor_data: dict,
        thresholds: dict,
        actuator=None
    ) -> bool:

        # moisture = sensor_data.get("moisture", 0)
        # water_level = sensor_data.get("water_level", 0)

        # if water_level < thresholds.get("water_level_min", 20):
        #     logger.warning(
        #         f"Cannot turn on pump: Water level too low ({water_level}%)"
        #     )
        #     return False

        # return moisture < thresholds.get("moisture_min", 30)

        # moisture = sensor_data.get("moisture") 
        # water_level = sensor_data.get("water_level") 
        # water_level_min = thresholds.get("water_level_min", 5) 
        # moisture_min = thresholds.get("moisture_min", 30) 
        
        # # Missing water-level reading -> do not activate pump
        # if water_level is None: 
        #     logger.warning( "Cannot evaluate pump: Water level sensor data unavailable" ) 
        #     return False 
        
        # # Water level too low -> do not activate pump 
        # if safe_lt(water_level, water_level_min): 
        #     logger.warning( f"Cannot turn on pump: Water level too low ({water_level}%)" ) 
        #     return False 
        
        # # Missing moisture reading -> do not activate pump 
        # if moisture is None: 
        #     logger.warning( "Cannot evaluate pump: Moisture sensor data unavailable" ) 
        #     return False 
        
        # # Activate only when moisture is below minimum 
        # return safe_lt(moisture, moisture_min)    

        moisture = sensor_data.get("moisture")
        water_level = sensor_data.get("water_level")

        if safe_lt(water_level, thresholds.get("water_level_min", 20)):
            logger.warning(
                f"Cannot turn on pump: Water level too low ({water_level}%)"
            )
            return False

        return safe_lt(moisture, thresholds.get("moisture_min", 30))     

