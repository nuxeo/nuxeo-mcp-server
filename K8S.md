# Deploying Nuxeo MCP Server on Kubernetes

This guide provides instructions for deploying the Nuxeo MCP Server on Kubernetes.

## Prerequisites

- Kubernetes cluster (e.g., Minikube, GKE, EKS, AKS)
- `kubectl` command-line tool configured to communicate with your cluster
- Docker image of the Nuxeo MCP Server (built as described in the README.md)

## Kubernetes Configuration Files

### Deployment

Create a file named `nuxeo-mcp-deployment.yaml` with the following content:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nuxeo-mcp-server
  labels:
    app: nuxeo-mcp-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nuxeo-mcp-server
  template:
    metadata:
      labels:
        app: nuxeo-mcp-server
    spec:
      containers:
      - name: nuxeo-mcp-server
        image: nuxeo-mcp-server:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8181
        env:
        - name: NUXEO_URL
          valueFrom:
            configMapKeyRef:
              name: nuxeo-mcp-config
              key: nuxeo_url
        - name: NUXEO_USERNAME
          valueFrom:
            secretKeyRef:
              name: nuxeo-mcp-secret
              key: username
        - name: NUXEO_PASSWORD
          valueFrom:
            secretKeyRef:
              name: nuxeo-mcp-secret
              key: password
        - name: MCP_MODE
          valueFrom:
            configMapKeyRef:
              name: nuxeo-mcp-config
              key: mcp_mode
        - name: MCP_PORT
          valueFrom:
            configMapKeyRef:
              name: nuxeo-mcp-config
              key: mcp_port
        - name: MCP_HOST
          valueFrom:
            configMapKeyRef:
              name: nuxeo-mcp-config
              key: mcp_host
        livenessProbe:
          httpGet:
            path: /health
            port: 8181
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8181
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
        resources:
          limits:
            cpu: "1"
            memory: "512Mi"
          requests:
            cpu: "0.5"
            memory: "256Mi"
```

### Service

Create a file named `nuxeo-mcp-service.yaml` with the following content:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nuxeo-mcp-server
  labels:
    app: nuxeo-mcp-server
spec:
  type: ClusterIP
  ports:
  - port: 8181
    targetPort: 8181
    protocol: TCP
    name: http
  selector:
    app: nuxeo-mcp-server
```

### ConfigMap

Create a file named `nuxeo-mcp-configmap.yaml` with the following content:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nuxeo-mcp-config
data:
  nuxeo_url: "http://nuxeo-service:8080/nuxeo"
  mcp_mode: "sse"
  mcp_port: "8181"
  mcp_host: "0.0.0.0"
```

### Secret

Create a file named `nuxeo-mcp-secret.yaml` with the following content:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: nuxeo-mcp-secret
type: Opaque
stringData:
  username: "Administrator"
  password: "Administrator"
```

## Deployment Steps

1. **Create the ConfigMap and Secret**:

   ```bash
   kubectl apply -f nuxeo-mcp-configmap.yaml
   kubectl apply -f nuxeo-mcp-secret.yaml
   ```

2. **Deploy the Nuxeo MCP Server**:

   ```bash
   kubectl apply -f nuxeo-mcp-deployment.yaml
   ```

3. **Create the Service**:

   ```bash
   kubectl apply -f nuxeo-mcp-service.yaml
   ```

## Verification

1. **Check if the pod is running**:

   ```bash
   kubectl get pods -l app=nuxeo-mcp-server
   ```

2. **Check the logs**:

   ```bash
   kubectl logs -l app=nuxeo-mcp-server
   ```

3. **Test the health endpoint**:

   ```bash
   # Port-forward the service to your local machine
   kubectl port-forward svc/nuxeo-mcp-server 8181:8181
   
   # In another terminal, test the health endpoint
   curl http://localhost:8181/health
   ```

   You should receive a response like:
   ```json
   {"status":"ok"}
   ```

## Exposing the Service

Every client that reaches the service acts as the Nuxeo user in `nuxeo-mcp-secret`: the server runs in `local` auth mode, one Nuxeo identity shared by all callers (see [Authentication Mode](README.md#authentication-mode)). Expose it only to callers who may all act as that user.

### Using Ingress

If you want to expose the service outside the cluster using an Ingress controller, create a file named `nuxeo-mcp-ingress.yaml` with the following content:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nuxeo-mcp-server
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: mcp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nuxeo-mcp-server
            port:
              number: 8181
```

Apply the Ingress configuration:

```bash
kubectl apply -f nuxeo-mcp-ingress.yaml
```

### Using LoadBalancer

Alternatively, you can expose the service using a LoadBalancer by modifying the service type:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nuxeo-mcp-server
  labels:
    app: nuxeo-mcp-server
spec:
  type: LoadBalancer
  ports:
  - port: 8181
    targetPort: 8181
    protocol: TCP
    name: http
  selector:
    app: nuxeo-mcp-server
```

## Horizontal Pod Autoscaling

To automatically scale the deployment based on CPU utilization, create a file named `nuxeo-mcp-hpa.yaml` with the following content:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nuxeo-mcp-server
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nuxeo-mcp-server
  minReplicas: 1
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 80
```

Apply the HPA configuration:

```bash
kubectl apply -f nuxeo-mcp-hpa.yaml
```

## Cleanup

To remove all the resources created for the Nuxeo MCP Server:

```bash
kubectl delete deployment nuxeo-mcp-server
kubectl delete service nuxeo-mcp-server
kubectl delete configmap nuxeo-mcp-config
kubectl delete secret nuxeo-mcp-secret
kubectl delete ingress nuxeo-mcp-server
kubectl delete hpa nuxeo-mcp-server
