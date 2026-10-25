import aws_cdk as cdk

from tasklane_infra.app_builder import build
from tasklane_infra.config import DEV

app = cdk.App()
build(app, DEV)
app.synth()
