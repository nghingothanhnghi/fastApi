# app/core/i18n/dependency.py

from fastapi import Request

from .config import DEFAULT_LOCALE
from .translator import Translator
from app.core.logging_config import get_logger 


logger = get_logger(__name__)

def get_locale(request: Request) -> str: 
    locale = getattr( 
        request.state, 
        "locale", 
        DEFAULT_LOCALE, 
    ) 
    
    logger.info( 
        "[i18n] cookie=%r state_locale=%r", 
        request.cookies.get("lang"), 
        locale, 
    )
    
    return locale


def get_translator(request: Request) -> Translator: 
    locale = get_locale(request) 
    translator = Translator(locale) 

    logger.info( 
        "[i18n] Translator locale=%r", 
        translator.locale, 
    )
    
    return translator