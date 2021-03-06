/* Copyright 2015 The TensorFlow Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================*/

#include "tensorflow/tools/graph_transforms/fold_constants_lib.h"

#include "tensorflow/core/common_runtime/constant_folding.h"
#include "tensorflow/core/graph/graph_constructor.h"
#include "tensorflow/core/graph/node_builder.h"
#include "tensorflow/core/graph/subgraph.h"
#include "tensorflow/core/public/session.h"
#include "tensorflow/tools/graph_transforms/transform_utils.h"

namespace tensorflow {
namespace graph_transforms {

Status ReplaceSendRecvs(const GraphDef& original_graph_def,
                        const GraphDef& rewritten_graph_def,
                        const std::vector<string>& inputs,
                        const std::vector<string>& outputs,
                        GraphDef* output_graph_def) {
  std::map<string, const NodeDef*> original_map;
  MapNamesToNodes(original_graph_def, &original_map);
  std::map<string, string> new_node_names;
  for (const NodeDef& node : rewritten_graph_def.node()) {
    // If the op isn't a Recv, or it was in the original, nothing to do.
    if ((node.op() != "_Recv") || (original_map.count(node.name()) == 1)) {
      continue;
    }
    // See if it matches an input from the original.
    for (const string& input : inputs) {
      // Here we rely on the naming convention for the Recv nodes that
      // RewriteGraphForExecution adds in the place of the feed inputs.
      string input_prefix = "_recv_" + input + "_";
      if (StringPiece(node.name()).starts_with(input_prefix)) {
        // If it does, prepare to rename any inputs that refer to it.
        new_node_names[node.name()] = input;
      }
    }
  }

  std::vector<NodeDef> nodes_to_add;
  for (const NodeDef& node : rewritten_graph_def.node()) {
    if ((node.op() == "_Send") || (node.op() == "_Recv")) {
      // If the op is a Send or Recv that wasn't in the original, skip it.
      if (original_map.count(node.name()) == 0) {
        continue;
      }
    }
    NodeDef new_node;
    new_node.CopyFrom(node);
    new_node.mutable_input()->Clear();
    for (const string& old_input : node.input()) {
      string input_prefix;
      string input_node_name;
      string input_suffix;
      NodeNamePartsFromInput(old_input, &input_prefix, &input_node_name,
                             &input_suffix);
      string new_input;
      if (new_node_names.count(input_node_name) > 0) {
        new_input =
            input_prefix + new_node_names[input_node_name] + input_suffix;
      } else {
        new_input = old_input;
      }
      *(new_node.mutable_input()->Add()) = new_input;
    }
    nodes_to_add.push_back(new_node);
  }
  for (std::pair<string, string> entry : new_node_names) {
    string removed_node_name = entry.second;
    const NodeDef* removed_node = original_map[removed_node_name];
    NodeDef new_node;
    new_node.CopyFrom(*removed_node);
    nodes_to_add.push_back(new_node);
  }

  for (const NodeDef& node : nodes_to_add) {
    output_graph_def->mutable_node()->Add()->CopyFrom(node);
  }
  return Status::OK();
}

Status RemoveUnusedNodes(const GraphDef& input_graph_def,
                         const std::vector<string>& inputs,
                         const std::vector<string>& outputs,
                         GraphDef* output_graph_def) {
  std::map<string, const NodeDef*> node_map;
  MapNamesToNodes(input_graph_def, &node_map);

  std::map<string, bool> used_nodes;
  for (const string& input : inputs) {
    used_nodes[input] = true;
  }
  std::vector<string> current_nodes = outputs;
  while (!current_nodes.empty()) {
    std::vector<string> next_nodes;
    for (const string& node_name : current_nodes) {
      used_nodes[node_name] = true;
      if (node_map.count(node_name) == 0) {
        LOG(ERROR) << "Bad graph structure, no node named '" << node_name
                   << "' found for input lookup";
        return errors::InvalidArgument("Bad graph structure, no node named '",
                                       node_name, "' found for input lookup");
      }
      const NodeDef& node = *(node_map[node_name]);
      for (const string& input_name : node.input()) {
        const string& input_node_name = NodeNameFromInput(input_name);
        if (used_nodes.count(input_node_name) == 0) {
          next_nodes.push_back(input_node_name);
        }
      }
    }
    current_nodes = next_nodes;
  }
  FilterGraphDef(
      input_graph_def,
      [&](const NodeDef& node) { return used_nodes.count(node.name()) > 0; },
      output_graph_def);

  return Status::OK();
}

Status FoldConstants(const GraphDef& input_graph_def,
                     const std::vector<string>& inputs,
                     const std::vector<string>& outputs,
                     GraphDef* output_graph_def) {
  Graph input_graph(OpRegistry::Global());
  ImportGraphDefOptions import_opts;
  TF_RETURN_IF_ERROR(
      ImportGraphDef(import_opts, input_graph_def, &input_graph, nullptr));
  DeviceAttributes device_attributes;
  TF_RETURN_IF_ERROR(subgraph::RewriteGraphForExecution(
      &input_graph, inputs, outputs, {}, device_attributes));
  DoConstantFolding(ConstantFoldingOptions(), nullptr, Env::Default(), nullptr,
                    &input_graph);
  GraphDef folded_graph_def;
  input_graph.ToGraphDef(&folded_graph_def);
  GraphDef send_recvs_replaced;
  TF_RETURN_IF_ERROR(ReplaceSendRecvs(input_graph_def, folded_graph_def, inputs,
                                      outputs, &send_recvs_replaced));
  TF_RETURN_IF_ERROR(RemoveUnusedNodes(send_recvs_replaced, inputs, outputs,
                                       output_graph_def));
  return Status::OK();
}

}  // namespace graph_transforms
}  // namespace tensorflow
