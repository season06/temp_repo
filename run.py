from pydantic import BaseModel
from abc import ABC, abstractmethod
import pandas as pd

class SopContext(BaseModel):
    sop_id: str
    ver: int
    info: pd.DataFrame

    class Config:
        arbitrary_types_allowed = True
    
class Pipeline:
    stages: list
    sop_ctx: SopContext

    def __init__(self):
        self.stages = []
        self.sop_ctx = None

    def set_attr(self, attr, value): ##
        setattr(self, attr, value)
    
    def get_attr(self, attr): ##
        return getattr(self, attr)
    
    def add_stage(self, stage, **kwargs):
        if not issubclass(stage, StageInterface):  ##
            raise ValueError(f'Class `{stage.__name__}` must be an instance of StageInterface')

        self.stages.append((stage, kwargs)) ## type
        return self
    
    def execute(self):
        for stage, kwargs in self.stages:
            print(f"{stage.__name__} Running...")
            stage(self).run(self.sop_ctx, **kwargs) ##

class StageInterface(ABC):
    pipe: Pipeline
    def __init__(self, pipeline: Pipeline):
        self.pipe = pipeline

    @abstractmethod
    def run(self):
        raise NotImplementedError

### Implement ###

class InitStage(StageInterface):
    def run(self, _, sop_id, ver):
        sop_ctx = SopContext(  ## pipeline attribute init
            sop_id=sop_id, 
            ver=ver, 
            info=pd.DataFrame()
        )
        self.pipe.set_attr('sop_ctx', sop_ctx)
        print(f"ctx {self.pipe.sop_ctx}")

class StageA(StageInterface):
    def run(self, sop_ctx):
        if sop_ctx.ver == 1:
            print('version 1')
        self.pipe.set_attr(
            'sop_ctx', 
            sop_ctx.model_copy(update={'ver': sop_ctx.ver + 1})
        )
        print(self.pipe.get_attr('sop_ctx').ver)
            
class StageB(StageInterface):
    def run(self, sop_ctx):
        print(sop_ctx.ver)


if __name__ == '__main__':
    pl = Pipeline()

    pl.add_stage(InitStage, sop_id='123', ver=1) \
      .add_stage(StageA) \
      .add_stage(StageB)
    
    pl.execute()