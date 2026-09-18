import os
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class LocalSecurity:
    """
    LocalSecurity utilizes Microsoft Presidio to analyze and scrub 
    personally identifiable information (PII), secrets, and other 
    sensitive data from text streams.
    """
    def __init__(self):
        # Initialize Presidio Analyzer and Anonymizer
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def scrub_text(self, text: str) -> str:
        if not text:
            return text
            
        # Analyze the text for sensitive information (PII, credentials, etc.)
        # Default entities include EMAIL_ADDRESS, PHONE_NUMBER, IP_ADDRESS, etc.
        results = self.analyzer.analyze(text=text, language='en')
        
        # Anonymize the detected entities (replaces with <ENTITY_TYPE>)
        anonymized_result = self.anonymizer.anonymize(text=text, analyzer_results=results)
        
        return anonymized_result.text
