# Account bootstrap (outside CDK)
`github-oidc.json` is the CloudFormation template for stack `tasklane-github-oidc`: the GitHub OIDC provider and the
`tasklane-gh-deploy-dev` role (trust: `repo:avishekdas@5960956/sundaydotcom@1433274253:environment:dev` — GitHub
issues subjects with immutable owner/repo ids for this repository). It may assume the CDK bootstrap roles, invoke
the migrate λ, and read the e2e test-user secrets. CDK bootstrap itself ran once through a short-lived admin role
(environment `dev-bootstrap`) that was deleted afterwards.
