import logging
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
class StageInterface(ABC):
    @abstractmethod
    def process(self, context):
        raise NotImplementedError("Subclasses must implement process()")

class APM:
    def __init__(self):
        self.db_client = None

    def get_apm_event(self):
        sql = ''
        result = {
            'start_time': datetime.now()+timedelta(days=-1),
            'end_time': datetime.now()+timedelta(days=1)
        }
        return result

    def is_in_apm_duration(self, start_time, end_time):
        current_time = datetime.now()
        if start_time <= current_time <= end_time:
            return True
        return False
    
    @abstractmethod
    def handle_status(self, event, context):
        raise NotImplementedError("Subclasses must implement handle_status()")
    
    def execute(self):
        event = self.get_apm_event()
        if event is None:
            logging.info('No event found')
            return False
        
        if not self.is_in_apm_duration(event['start_time'], event['end_time']):
            logging.info('Not in APM duration')
            return False
        
        self.handle_status()

class Stage1(StageInterface, APM):
    def __init__(self):
        super().__init__()
    
    def process(self, context):
        self.execute()
    
    def handle_status(self):
        logging.info('Handling status in Stage1')

if __name__ == '__main__':
    stage1 = Stage1()
    stage1.process(None)