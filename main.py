from abc import ABC, abstractmethod
from typing import Any
import pydantic


class PipelineContext:
    def __init__(self):
        self.stages = []
        self.is_immutable = True

    @staticmethod
    def _validate(stage):
        if not isinstance(stage, StageInterface):
            raise ValueError(f'Class `{stage.__class__.__name__}` must be an instance of StageInterface')

    def add_stage(self, stage: Any) -> None:
        self._validate(stage)
        self.stages.append(stage)

    def run(self) -> None:
        result = None
        for obj in self.stages:
            result = obj.execute(result)
            print(f"{obj.__class__.__name__}: {result}")

class StageInterface(ABC):
    def __init__(self):
        sop_id: str
        # ctx: SopModel
        # if getattr(obj, 'conditions').get('test'):

    @abstractmethod
    def execute(self):
        raise NotImplementedError

# class SopModel(pydantic.BaseModel):
#     id:
#     candidates:

"""""""""################"""""""""

class SqlQuery(StageInterface):
    def __init__(self):
        super().__init__()
        # self.stage_ctx = StageCtx(
        #     id=id,
        #     candidates=candidates
        # )

    def execute(self, candidate):
        return [1, 2]

class EnvFilter(StageInterface):
    def __init__(self):
        super().__init__()

    def execute(self, candidate):
        return [1]

class Test1(StageInterface):
    def __init__(self):
        pass

    def filter(self, candidate):
        return [1]
    
# class Test2:
#     def __init__(self):
#         pass
#     def execute(self, candidate):
#         return [1]
    
if __name__ == '__main__':
    sql_query = SqlQuery()
    env_filter = EnvFilter()
    test1 = Test1()
    # test2 = Test2()

    pipeline = PipelineContext()
    pipeline.add_stage(sql_query)
    pipeline.add_stage(env_filter)
    pipeline.add_stage(test1)
    # pipeline.add_stage(test2)
    pipeline.run()

# https://ithelp.ithome.com.tw/articles/10223418