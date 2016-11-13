#!/usr/bin/python
# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Generates YAML configuration files for distributed TensorFlow workers.

The workers will be run in a Kubernetes (k8s) container cluster.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import sys

# Note: It is intentional that we do not import tensorflow in this script. The
# machine that launches a TensorFlow k8s cluster does not have to have the
# Python package of TensorFlow installed on it.


DEFAULT_DOCKER_IMAGE = 'tensorflow/tf_grpc_test_server'
DEFAULT_PORT = 2222

# TODO(cais): Consider adding resource requests/limits to the pods.

# Worker pods will mount host volume /shared, as a convenient way to create
# shared storage among workers during local tests.
# WORKER_RC = (
#     """apiVersion: v1
# kind: ReplicationController
# metadata:
#   name: tf-worker{worker_id}
# spec:
#   replicas: 1
#   template:
#     metadata:
#       labels:
#         tf-worker: "{worker_id}"
#     spec:
#       containers:
#       - name: tf-worker{worker_id}
#         image: {docker_image}
#         args:
#           - --cluster_spec={cluster_spec}
#           - --job_name=worker
#           - --task_id={worker_id}
#         ports:
#         - containerPort: {port}
#         volumeMounts:
#         - name: shared
#           mountPath: /shared
#       volumes:
#       - name: shared
#         hostPath:
#           path: /shared
# """)
PETSET_TEMPLATE = (
  """apiVersion: v1
kind: Service
metadata:
  name: tf-{job_name}
  labels:
    tf: {job_name}
spec:
  type: {service_type}
  ports:
  - port: {port}
  # *.tf-{job_name}.default.svc.cluster.local
  selector:
    tf: {job_name}
---
apiVersion: apps/v1alpha1
kind: PetSet
metadata:
  name: tf-{job_name}
spec:
  serviceName: tf-{job_name}
  replicas: {replicas}
  template:
    metadata:
      labels:
        tf: {job_name}
    spec:
      terminationGracePeriodSeconds: 0
      containers:
      - name: tf-{job_name}
        image: {docker_image}
        args:
          - --cluster_spec={cluster_spec}
          - --job_name={job_name}
        ports:
        - containerPort: {port}
        volumeMounts:
        - name: shared
          mountPath: /shared
      volumes:
      - name: shared
        hostPath:
          path: /shared
""")
# PARAM_SERVER_RC = (
#     """apiVersion: v1
# kind: ReplicationController
# metadata:
#   name: tf-ps{param_server_id}
# spec:
#   replicas: 1
#   template:
#     metadata:
#       labels:
#         tf-ps: "{param_server_id}"
#     spec:
#       containers:
#       - name: tf-ps{param_server_id}
#         image: {docker_image}
#         args:
#           - --cluster_spec={cluster_spec}
#           - --job_name=ps
#           - --task_id={param_server_id}
#         ports:
#         - containerPort: {port}
#         volumeMounts:
#         - name: shared
#           mountPath: /shared
#       volumes:
#       - name: shared
#         hostPath:
#           path: /shared
# """)
# PARAM_SERVER_SVC = (
#     """apiVersion: v1
# kind: Service
# metadata:
#   name: tf-ps{param_server_id}
#   labels:
#     tf-ps: "{param_server_id}"
# spec:
#   ports:
#   - port: {port}
#   selector:
#     tf-ps: "{param_server_id}"
# """)
# PARAM_LB_SVC = ("""apiVersion: v1
# kind: Service
# metadata:
#   name: tf-ps{param_server_id}
#   labels:
#     tf-ps: "{param_server_id}"
# spec:
#   type: LoadBalancer
#   ports:
#   - port: {port}
#   selector:
#     tf-ps: "{param_server_id}"
# """)


def main():
  """Do arg parsing."""
  parser = argparse.ArgumentParser()
  parser.add_argument('--num_workers',
                      type=int,
                      default=2,
                      help='How many worker pods to run')
  parser.add_argument('--num_parameter_servers',
                      type=int,
                      default=1,
                      help='How many paramater server pods to run')
  parser.add_argument('--grpc_port',
                      type=int,
                      default=DEFAULT_PORT,
                      help='GRPC server port (Default: %d)' % DEFAULT_PORT)
  parser.add_argument('--request_load_balancer',
                      type=bool,
                      default=False,
                      help='To request worker0 to be exposed on a public IP '
                      'address via an external load balancer, enabling you to '
                      'run client processes from outside the cluster')
  parser.add_argument('--docker_image',
                      type=str,
                      default=DEFAULT_DOCKER_IMAGE,
                      help='Override default docker image for the TensorFlow '
                      'GRPC server')
  args = parser.parse_args()

  if args.num_workers <= 0:
    sys.stderr.write('--num_workers must be greater than 0; received %d\n'
                     % args.num_workers)
    sys.exit(1)
  if args.num_parameter_servers <= 0:
    sys.stderr.write(
        '--num_parameter_servers must be greater than 0; received %d\n'
        % args.num_parameter_servers)
    sys.exit(1)

  # Generate contents of yaml config
  yaml_config = GenerateConfig(args.num_workers,
                               args.num_parameter_servers,
                               args.grpc_port,
                               args.request_load_balancer,
                               args.docker_image)
  print(yaml_config)  # pylint: disable=superfluous-parens


def GenerateConfig(num_workers,
                   num_parameter_servers,
                   port,
                   request_load_balancer,
                   docker_image):
  """Generate configuration strings."""
  config = ''

  # If request load balancer, set service type to LoadBalancer
  # otherwise, use the default type ClusterIP
  if request_load_balancer:
    service_type = "LoadBalancer"
  else:
    service_type = "ClusterIP"

  cluster_spec = ClusterSpecString(num_workers,
                       num_parameter_servers,
                       port)

  # Generate the petset and service for the worker job servers """
  config += PETSET_TEMPLATE.format(
        port=port,
        job_name="worker",
        docker_image=docker_image,
        service_type=service_type,
        replicas=num_workers,
        cluster_spec=cluster_spec)
  config += '---\n'

  # Generate the petset and service for the parameter servers
  config += PETSET_TEMPLATE.format(
        port=port,
        job_name="ps",
        docker_image=docker_image,
        service_type=service_type,
        replicas=num_parameter_servers,
        cluster_spec=cluster_spec)

  return config

def ClusterSpecString(num_workers,
                      num_parameter_servers,
                      port):
  """Generates the cluster spec."""

  # Kubernetes guarantees us ordinal numbering for petsets
  # so that for n replicas of a tf-worker
  # we will have DNS entries for 
  # tf-worker-1.default, tf-worker-2.default, etc.

  spec = 'worker|'
  for worker in range(num_workers):
    spec += 'tf-worker-%d:%d' % (worker, port)
    if worker != num_workers-1:
      spec += ';'

  spec += ',ps|'
  for param_server in range(num_parameter_servers):
    spec += 'tf-ps-%d:%d' % (param_server, port)
    if param_server != num_parameter_servers-1:
      spec += ';'

  return spec


if __name__ == '__main__':
  main()
