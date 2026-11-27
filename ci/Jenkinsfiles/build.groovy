/*
 * (C) Copyright 2026 Nuxeo (http://nuxeo.com/) and others.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Contributors:
 *     Antoine Taillefer <antoine.taillefer@hyland.com>
 */
library identifier: 'platform-ci-shared-library@v0.0.91'

String getVersion() {
  return "sha-${env.GIT_COMMIT.take(7)}"
}

List<String> getNuxeoLTSVersions() {
  return ['2023', '2025', '2027']
}

List<String> getTestPackages(String lts) {
  def packages = ['nuxeo-web-ui']
  // 2023 ships its search and audit backends; later LTS install them as packages.
  if (lts != '2023') {
    def opensearch = lts == '2027' ? 'opensearch3' : 'opensearch1'
    packages += ["nuxeo-audit-${opensearch}", "nuxeo-search-client-${opensearch}"]
  }
  return packages
}

boolean isPreprodTag(String nuxeoTag) {
  // target connect preprod if nuxeo tag is a build tag or a moving tag
  return nuxeoTag.matches("^\\d+\\.(x|\\d+\\.\\d+)\$")
}

Closure integrationTests(String lts) {
  // TODO: remove once 2027 is released, nuxeo:2027 doesn't exist yet
  def nuxeoTag = lts == '2027' ? '2027.x' : lts
  return {
    stage("Nuxeo ${lts}") {
      container('base') {
        def branch = env.BRANCH_NAME.toLowerCase().replaceAll('[^a-z0-9-]', '-').take(15)
        def namespace = "${CURRENT_NAMESPACE}-mcp-server-${branch}-${BUILD_NUMBER}-${lts}".toLowerCase()
        def testImageTag = "${lts}-${VERSION}-${BUILD_NUMBER}"
        def nuxeoVersion = nxDocker.getLabel(image: "${PRIVATE_DOCKER_REGISTRY}/nuxeo/nuxeo:${nuxeoTag}", label: 'org.nuxeo.version')
        def clidSecret = isPreprodTag(nuxeoTag) ? 'instance-clid-preprod' : 'instance-clid'
        def connectUrl = isPreprodTag(nuxeoTag) ? CONNECT_PREPROD_SITE_URL : CONNECT_PROD_SITE_URL
        def clid = nxK8s.getSecretData(namespace: 'platform', name: clidSecret, key: 'instance\\.clid')
        withEnv(["CLID=${clid}"]) {
          nxDocker.build(
            skaffoldFile: 'ci/docker/skaffold.yaml',
            envVars: [
              "NUXEO_VERSION=${nuxeoVersion}",
              "FTESTS_VERSION=${testImageTag}",
              "CONNECT_URL=${connectUrl}",
              // Comma-separated: docker-buildx splits build args on spaces.
              "NUXEO_PACKAGES=${getTestPackages(lts).join(',')}",
            ]
          )
        }
        nxWithHelmfileDeployment(
          namespace: namespace,
          environment: 'integration-tests',
          cacheName: "mcp-server-${lts}",
          secrets: [[name: clidSecret, namespace: 'platform']],
          envVars: [
            "NUXEO_VERSION=${nuxeoVersion}",
            "FTESTS_VERSION=${testImageTag}",
            "CONNECT_CLID_SECRET=${clidSecret}",
            "MCP_IMAGE_DIGEST=${env.MCP_IMAGE_DIGEST}",
            "NUXEO_URL=http://nuxeo.${namespace}.svc.cluster.local/nuxeo",
            "MCP_URL=http://mcp.${namespace}.svc.cluster.local:8181/mcp",
          ]) {
          // Not in envVars: Helmfile would send <REPO>_USERNAME/_PASSWORD to the `nuxeo` Helm repository.
          withEnv(['NUXEO_USERNAME=Administrator', 'NUXEO_PASSWORD=Administrator']) {
            sh '''
              uv run python seed_nuxeo.py \
                --url "$NUXEO_URL" \
                --username "$NUXEO_USERNAME" \
                --password "$NUXEO_PASSWORD"
            '''
            nxWithGitHubStatus(context: "tests/smoke/${lts}", message: "Smoke tests - Nuxeo ${lts}") {
              // A new Service can be unreachable from the agent for a few seconds after its pod is Ready.
              sh """
                curl --fail --silent --show-error --output /dev/null \
                  --retry 30 --retry-delay 2 --retry-all-errors \
                  "${env.MCP_URL.replaceFirst('/mcp$', '/health')}"
              """
              sh '''
                uv run python mcp_client.py --url "$MCP_URL" search "SELECT * FROM Document WHERE ecm:primaryType = 'File'"
                uv run python mcp_client.py --url "$MCP_URL" get-document --path /default-domain
              '''
            }
            nxWithGitHubStatus(context: "tests/integration/${lts}", message: "Integration tests - Nuxeo ${lts}") {
              try {
                sh "uv run pytest tests/ -v --integration -m integration --junitxml=reports/integration-${lts}.xml"
              } finally {
                junit allowEmptyResults: true, testResults: "reports/integration-${lts}.xml"
              }
            }
          }
        }
      }
    }
  }
}

pipeline {
  agent {
    label 'jenkins-base'
  }
  options {
    buildDiscarder(logRotator(daysToKeepStr: '60', numToKeepStr: '60', artifactNumToKeepStr: '5'))
    disableConcurrentBuilds(abortPrevious: true)
    githubProjectProperty(projectUrlStr: 'https://github.com/nuxeo/nuxeo-mcp-server')
    timeout(time: 2, unit: 'HOURS')
  }
  environment {
    BASE_REGISTRY = 'dhi.io'
    CURRENT_NAMESPACE = nxK8s.getCurrentNamespace()
    INTERNAL_REGISTRY = 'docker-internal.packages.nuxeo.com'
    PATH = "${WORKSPACE}/.ci-bin:${env.PATH}"
    // On the workspace volume, like .venv, so uv hardlinks instead of copying.
    UV_CACHE_DIR = '/home/jenkins/.cache/uv'
    VERSION = getVersion()
  }
  stages {
    stage('Set labels') {
      steps {
        container('base') {
          script {
            nxK8s.setPodLabels()
          }
        }
      }
    }
    stage('Setup') {
      steps {
        container('base') {
          sh 'ci/setup.sh'
        }
      }
    }
    stage('Build') {
      steps {
        container('base') {
          nxWithGitHubStatus(context: 'python/build', message: 'Build') {
            sh 'uv build'
          }
        }
      }
    }
    stage('Static checks') {
      steps {
        container('base') {
          nxWithGitHubStatus(context: 'python/checks', message: 'Static checks') {
            sh '''
              uv run black --check src/ tests/
              uv run isort --check-only src/ tests/
              uv run mypy src/
              uv run python scripts/generate_tool_reference.py --check
              uv run python scripts/add_license_headers.py --check
            '''
          }
        }
      }
    }
    stage('Unit tests') {
      steps {
        container('base') {
          nxWithGitHubStatus(context: 'tests/unit', message: 'Unit tests') {
            sh 'uv run pytest tests/ -v --no-integration --junitxml=reports/unit.xml'
          }
        }
      }
      post {
        always {
          junit allowEmptyResults: true, testResults: 'reports/unit.xml'
        }
      }
    }
    stage('Build image') {
      steps {
        container('base') {
          nxWithGitHubStatus(context: 'docker/build', message: 'Build image') {
            script {
              // The digest this build pushed, rather than resolving the tag again.
              nxDocker.build(
                skaffoldFile: 'skaffold.yaml',
                envVars: ['SKAFFOLD_FILE_OUTPUT=image-build.json']
              )
              env.MCP_IMAGE_DIGEST = sh(
                returnStdout: true,
                script: "jq -r '.builds[0].tag | split(\"@\")[1]' image-build.json"
              ).trim()
            }
          }
        }
      }
    }
    stage('Tests') {
      steps {
        script {
          def branches = [:]
          for (lts in getNuxeoLTSVersions()) {
            branches["Nuxeo ${lts}"] = integrationTests(lts)
          }
          parallel branches
        }
      }
    }
    stage('Deploy image') {
      when {
        expression { nxUtils.isNotPullRequestAndNotDryRun() }
      }
      steps {
        container('base') {
          nxWithGitHubStatus(context: 'docker/deploy', message: 'Deploy image') {
            script {
              def source = "${DOCKER_REGISTRY}/nuxeo/nuxeo-mcp-server@${env.MCP_IMAGE_DIGEST}"
              nxDocker.copy(from: source, tos: [
                "${INTERNAL_REGISTRY}/nuxeo/nuxeo-mcp-server:${VERSION}",
                "${INTERNAL_REGISTRY}/nuxeo/nuxeo-mcp-server:${BRANCH_NAME}",
              ], options: '--all --preserve-digests')
            }
          }
        }
      }
    }
  }
  post {
    always {
      script {
        nxUtils.setBuildDescription()
        nxJira.updateIssues()
        nxUtils.notifyBuildStatusIfNecessary()
      }
    }
  }
}
