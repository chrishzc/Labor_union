"""Advance established arrangements when their agreed actual start day arrives."""
class ServiceStartLifecycleWorkflow:
    def __init__(self,repository,units):
        self.repository,self.units=repository,units

    def advance_due(self,evaluation_at,page_size=100):
        after='';changed=0
        while True:
            cases=self.repository.due_cases(evaluation_at,after,page_size)
            if not cases:return changed
            for case in cases:
                with self.units() as unit:
                    changed+=int(self.repository.advance(case,evaluation_at))
                    unit.commit()
            after=cases[-1]
