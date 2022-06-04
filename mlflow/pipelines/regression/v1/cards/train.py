import os
from mlflow.pipelines.cards import BaseCard


class TrainCard(BaseCard):
    """
    Card for the ``train`` step of the v1 scikit-learn regression pipeline.

    TODO: Migrate the train card to a tab-based card, removing this class and its associated
          HTML template in the process.
    """

    def __init__(self, pipeline_name: str, step_name: str):
        super().__init__(
            template_root=os.path.join(os.path.dirname(__file__), "../resources"),
            template_name="train.html",
            pipeline_name=pipeline_name,
            step_name=step_name,
        )
