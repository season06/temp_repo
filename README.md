# Kustomization

ref: https://unruly-toast-932.notion.site/K8s-Ingress-and-Certificate-Setup-1b43d75eaf57802c938ed18257453d7f

## Directory
```
kustomize/
├── base
│   └── resources
│       ├── certificate.yaml
│       ├── deployment.yaml
│       ├── ingress.yaml
│       └── service.yaml
└── overlays
    ├── dev
    |   ├──  kustomization.yaml
    |   └── podinfo-values.yaml
    └── prod
        ├──  kustomization.yaml
        └── podinfo-values.yaml

```
## Dry run
```
kustomize build .\kustomize\overlays\dev\ > output.yaml
```

# Helmfile

## Directory
```
helmfile/
├── helmfile.yaml
├── environments/
│   ├── dev.yaml
│   └── prod.yaml
└── templates/
    └── web-app/
        ├── Chart.yaml
        ├── templates/
        │   ├── deployment.yaml
        │   ├── service.yaml
        │   ├── ingress.yaml
        │   └── certificate.yaml
        └── values.yaml
```