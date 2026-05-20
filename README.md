# GCP Model Armor Enforcer

[![Security: Keyless](https://img.shields.io/badge/Security-Keyless-green.svg)](https://cloud.google.com/docs/authentication)
[![Infrastructure: Terraform](https://img.shields.io/badge/Infra-Terraform-blueviolet.svg)](https://www.terraform.io/)
[![Engine: Cloud Build](https://img.shields.io/badge/CI%2FCD-Google%20Cloud%20Build-blue.svg)](https://cloud.google.com/build)

An automated, secure, and highly scalable pipeline to discover, provision, and enforce **Google Cloud Model Armor** safety guardrails across complex GCP Folder or Organization hierarchies. 

Built natively for Google Cloud, this project eliminates static security keys and credentials. It leverages a keyless CI/CD architecture orchestrated entirely via Google Cloud Build, utilizing **Application Default Credentials (ADC)** and remote GCS state management.

---

## 📐 Architecture & Execution Flow

The enforcer operates in a sequential, two-step automated pipeline:

```mermaid
graph TD
    A[Cloud Build Trigger] --> B[Step 1: discover.py Script]
    B --> C{Project Vertex AI Enabled?}
    C -- Yes --> D[Target for Model Armor]
    C -- No & --force-model-armor --> D
    C -- No --> E[Skip Project]
    D --> F[Write to terraform.tfvars.json]
    F --> G[Step 2: terraform init]
    G --> H[Step 3: terraform plan]
    H --> I[Step 4: terraform apply]
    I --> J[Global Floor Setting enforced at Folder/Org]
    I --> K[Granular Templates provisioned in Target Projects]
```

1. **Intelligent Discovery (`discover.py`)**:
   - Recursively traverses the Folder or Organization hierarchy to find active GCP projects.
   - Checks whether the Service Usage API has `aiplatform.googleapis.com` (Vertex AI) active.
   - Integrates a robust **exponential backoff with jitter** algorithm to navigate Service Usage rate limits without triggering API rate-limiting blocks.
   - Generates a standardized `terraform.tfvars.json` containing target projects.
2. **Declarative Enforcement (Terraform)**:
   - Provisions a single central **Folder/Org-wide Floor Setting** (`google_model_armor_floorsetting`) that locks down prompt injection (`HIGH`), Malicious URIs (`ENABLED`), and RAI safety filters (`HIGH`).
   - Deploys regional **Model Armor Templates** (`google_model_armor_template`) into child projects, inheriting the folder's safety baseline while offering dynamic data-plane and template operation logging.

---

## 🛠️ Prerequisites

Before executing the deployment pipeline, ensure the following assets are ready:
1. **Google Cloud Folder or Organization ID**: The target node hierarchy to discover and enforce.
2. **Central Terraform State Bucket**: A secure Google Cloud Storage (GCS) bucket to maintain Terraform remote state.
3. **Google Cloud Build Environment**: Enable Cloud Build and Resource Manager APIs in your pipeline host project.

---

## 🔐 Required IAM Permissions

To run this architecture natively and keylessly, bind the following Folder/Org-level roles to your **Cloud Build Service Account** (`[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`):

| Role Name | Purpose | Scoped Level |
| :--- | :--- | :--- |
| **`roles/resourcemanager.folderViewer`** | Recursively browse subfolders under the hierarchy. | Folder/Org Level |
| **`roles/browser`** | Browse and discover downstream projects. | Folder/Org Level |
| **`roles/serviceusage.serviceUsageAdmin`** | Verify active APIs (Vertex AI status). | Folder/Org Level |
| **`roles/modelarmor.admin`** | Provision Floor Settings & Model Armor Templates. | Folder/Org Level |
| **`roles/storage.objectAdmin`** | Read/Write remote Terraform state files in GCS. | GCS State Bucket |

---

## 🚀 Implementation Guide

Follow these steps to trigger deployment from your local workstation or shell:

### Step 1: Clone the Repository
```bash
git clone https://github.com/[YOUR_ORG]/gcp-model-armor-enforcer.git
cd gcp-model-armor-enforcer
```

### Step 2: Run the Enforcer Pipeline

You have two options for providing your target Folder ID and GCS remote state bucket:

#### **Option A: Run Dynamically via Command Line (Recommended)**
Pass your configurations dynamically at runtime without modifying any repository files:

```bash
gcloud builds submit --config=cloudbuild.yaml \
    --substitutions=\
_PARENT_ID="folders/1234567890",\
_GCS_STATE_BUCKET="your-terraform-state-bucket-name"
```

#### **Option B: Hardcode Defaults in `cloudbuild.yaml`**
Open [cloudbuild.yaml](file:///usr/local/google/home/manishkgaur/Desktop/Workspace/gcp-model-armor-enforcer/cloudbuild.yaml) and modify the default values in the `substitutions:` block:

```yaml
substitutions:
  _PARENT_ID: 'folders/1234567890'                      # Target Folder/Org ID
  _GCS_STATE_BUCKET: 'your-terraform-state-bucket-name' # GCS State Bucket Name
```

Then trigger the build directly:
```bash
gcloud builds submit
```

---

### 🕵️ Running in Audit-Only Mode

If you want to run a hierarchy-wide security discovery and audit without deploying or mutating any GCP resources, run the Python script locally with the `--audit-only` flag:

```bash
# 1. Install the native GCP dependencies
pip3 install -r requirements.txt

# 2. Execute the discovery script in audit mode
python3 discover.py "folders/1234567890" --audit-only
```

This outputs a CSV report named **`model_armor_audit.csv`** detailing the Vertex AI integration status of all discovered child projects, without generating a target variables file or triggering Terraform.

---

## ⚙️ Configuration & Variables

### 1. Python Discovery Script Arguments (`discover.py`)
The discovery engine supports standard execution arguments:

*   `parent_id` (Positional): The Folder or Organization ID to scan (e.g., `folders/123456` or `organizations/789012`).
*   `--force-model-armor`: Forces targeting of projects even if Vertex AI is not active (Default: `true`).
*   `--audit-only`: Performs project scanning and writes reports (`model_armor_audit.csv`) without generating `terraform.tfvars.json`.

### 2. Terraform Root Variables
You can configure deployment characteristics via these root variables:

| Variable Name | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| `parent_id` | `string` | The target GCP Folder or Org ID (e.g., `folders/123456`). | *Required* |
| `location` | `string` | Regional location where the Model Armor Templates reside. | `us-central1` |
| `pii_inspection_enabled` | `bool` | Flag to toggle Sensitive Data Protection (PII) inspection. | `true` |
| `log_template_operations` | `bool` | Enables operational audit logging for templates. | `true` |
| `log_sanitize_operations` | `bool` | Logs prompt/response payloads (contains data payloads). | `false` |

---

## 🛡️ Security Considerations

*   **Keyless Authentication**: No static service account keys (`.json` keyfiles) are stored in the repository or injected into Cloud Build. Authentication relies strictly on native IAM workload credentials (ADC).
*   **Data-Plane Observability**: Data-plane payload logging (`log_sanitize_operations`) is set to `false` by default. Enable this parameter only in sandboxed/isolated environments to prevent unintended logging of Sensitive Data (PII) inside Cloud Logging.
*   **State Encryption**: Ensure your central GCS Terraform remote state bucket is configured with Customer-Managed Encryption Keys (CMEK) and Object Versioning enabled.
