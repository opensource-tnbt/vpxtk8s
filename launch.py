"""
Automation of Pod Deployment with Kubernetes Python API
"""

import os
import re
import logging
import json
import time
import yaml
import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

from conf import settings as S

_CURR_DIR = os.path.dirname(os.path.realpath(__file__))

class Papi():
    """
    Class for controlling the pod through PAPI
    """

    def __init__(self):
        """
        Initialisation function.
        """
        self._logger = logging.getLogger(__name__)

    def create(self):
        """
        Creation Process
        """
        print("Entering Create Function")
        config.load_kube_config(S.getValue('K8S_CONFIG_FILEPATH'))
        api = client.CoreV1Api()
        namespace = 'default'
        pod_manifests = S.getValue('POD_MANIFEST_FILEPATH')
        pod_count = int(S.getValue('POD_COUNT'))
        if S.hasValue('POD_NAMESPACE'):
            namespace = S.getValue('POD_NAMESPACE')
        dep_pod_list = []

        #create pod workloads
        api = client.CoreV1Api()
        for count in range(pod_count):
            dep_pod_info = {}
            pod_manifest = load_manifest(pod_manifests[count])
            dep_pod_info['name'] = pod_manifest["metadata"]["name"]
            try:
                response = api.create_namespaced_pod(namespace, pod_manifest)
                self._logger.info(str(response))
                self._logger.info("Created POD %d ...", self._number)
            except ApiException as err:
                raise Exception from err

            # Wait for the pod to start
            time.sleep(5)
            status = "Unknown"
            count = 0
            while True:
                if count == 10:
                    break
                try:
                    response = api.read_namespaced_pod_status(dep_pod_info['name'],
                            namespace)
                    status = response.status.phase
                except ApiException as err:
                    raise Exception from err
                if (status == "Running"
                        or status == "Failed"
                        or status == "Unknown"):
                    break
                else:
                    time.sleep(5)
                    count = count + 1
            # Now Get the Pod-IP
            try:
                response = api.read_namespaced_pod_status(dep_pod_info['name'],
                        namespace)
                dep_pod_info['pod_ip'] = response.status.pod_ip
            except ApiException as err:
                raise Exception from err
            dep_pod_info['namespace'] = namespace
            dep_pod_list.append(dep_pod_info)
            cmd = ['cat', '/etc/podnetinfo/annotations']
            execute_command(api, dep_pod_info, cmd)
        
        S.setValue('POD_LIST',dep_pod_list)
        return dep_pod_list

    def terminate(self):
        """
        Cleanup Process
        """
        #self._logger.info(self._log_prefix + "Cleaning vswitchperf namespace")
        self._logger.info("Terminating Pod")
        api = client.CoreV1Api()
        # api.delete_namespace(name="vswitchperf", body=client.V1DeleteOptions())

        if S.getValue('PLUGIN') == 'sriov':
            api.delete_namespaced_config_map(self._sriov_config, self._sriov_config_ns)


def load_manifest(filepath):
    """
    Reads k8s manifest files and returns as string

    :param str filepath: filename of k8s manifest file to read

    :return: k8s resource definition as string
    """
    with open(filepath) as handle:
        data = handle.read()

    try:
        manifest = json.loads(data)
    except ValueError:
        try:
            manifest = yaml.safe_load(data)
        except yaml.parser.ParserError as err:
            raise Exception from err

    return manifest

def replace_namespace(api, namespace):
    """
    Creates namespace if does not exists
    """
    namespaces = api.list_namespace()
    for nsi in namespaces.items:
        if namespace == nsi.metadata.name:
            api.delete_namespace(name=namespace,
                                 body=client.V1DeleteOptions())
            break

        time.sleep(0.5)
        api.create_namespace(client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)))

def execute_command(api_instance, pod_info, exec_command):
    """
    Execute a command inside a specified pod
    exec_command = list of strings
    """
    name = pod_info['name']
    resp = None
    try:
        resp = api_instance.read_namespaced_pod(name=name,
                                                namespace='default')
    except ApiException as e:
        if e.status != 404:
            print("Unknown error: %s" % e)
            exit(1)
    if not resp:
        print("Pod %s does not exist. Creating it..." % name)
        return -1

    # Calling exec and waiting for response
    resp = stream(api_instance.connect_get_namespaced_pod_exec,
                  name,
                  'default',
                  command=exec_command,
                  stderr=True, stdin=False,
                  stdout=True, tty=False)
    print("Response: " + resp)
    return resp

def get_virtual_sockets(api_instance, podname, namespace):
    """
    Memif or VhostUser Sockets
    """
    socket_files = []
    pinfo = {'name': podname,
             'pod_ip':'',
             'namespace': namespace}
    cmd = ['cat', '/etc/podnetinfo/annotations']
    resp = execute_command(api_instance, pinfo, cmd)
    # Remove unnecessary elements
    results = re.sub(r"(\\n|\"|\n|\\|\]|\{|\}|\[)", "", resp).strip()
    # Remove unnecessary spaces
    results = re.sub(r"\s+","", results, flags=re.UNICODE)
    # Get the RHS values
    output = results.split('=')
    for out in output:
        if 'socketfile' in out:
            out2 = out.split(',')
            for rout in out2:
                if 'socketfile' in rout:
                    print(rout[11:])
                    socket_files.append(rout[11:])


def get_sriov_interfaces(api_instance, podname, namespace):
    """
    Get SRIOV PIDs.
    """
    pinfo = {'name': podname,
             'pod_ip':'',
             'namespace': namespace}
    cmd = ['cat', '/etc/podnetinfo/annotations']
    response = execute_command(api_instance, pinfo, cmd)
    # Remove unnecessary elements
    results = re.sub(r"(\\n|\"|\n|\\|\]|\{|\}|\[)", "", response).strip()
    # Remove unnecessary spaces
    results = re.sub(r"\s+","", results, flags=re.UNICODE)
    # Get the RHS values
    output = results.split('=')
    names = []
    ifs = []
    for out in output:
        if 'interface' in out:
            out2 = out.split(',')
            for rout in out2:
                if 'interface' in rout:
                    ifs.append(rout[10:])
                elif 'name' in rout:
                    names.append(rout[5:])
    res = {names[i]: ifs[i] for i in range(len(names))}

def get_ip_details(api_instance, pod_name, namespace):
    """
    Get IP address of Non-Default Interfaces - If any
    """
    return


def main():
    """Main function.
    """
    # configure settings

    S.load_from_dir(os.path.join(_CURR_DIR, 'conf'))
    # define the timestamp to be used by logs and results
    date = datetime.datetime.fromtimestamp(time.time())
    timestamp = date.strftime('%Y-%m-%d_%H-%M-%S')
    S.setValue('LOG_TIMESTAMP', timestamp)

    results_dir = "results_" + timestamp
    results_path = os.path.join(S.getValue('LOG_DIR'), results_dir)
    S.setValue('RESULTS_PATH', results_path)

    # create results directory
    if not os.path.exists(results_path):
        os.makedirs(results_path)
    print("All Set")
    pod_ref = Papi()
    pod_ref.create()


if __name__ == "__main__":
    main()
