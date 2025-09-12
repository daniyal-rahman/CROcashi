## In Orchestrator.py
There should not be a block of pubmed imports. Pubmed ingestion should follow the same schema as all other pipelines. I belive that that would mean moving the pipeline.py file from ingest/pubmed into pipeline/ and renamed to be more descriptive, but the real goal is to make this a singular import in orchestrator and moving this multi import code into isolated pubmed file like the other pipelines.
This should also apply to the hooks for the other imports/pipelines that haven't been implemented. For these clean up the files and import to match the existing schema/repo struct.
    
PipelineExecutionResult seems a little off. It seems reduntant/ not used. I think that the orchestrator result is more closer to what we need and maybe some of of these values can be folded into that class instead. If you can explain a meaningfull difference in the usecases let me know (If this is the case stop here and let me respond with my thoughts)


