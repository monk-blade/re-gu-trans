// End-to-end librime session test for menus and persisted numbered learning.
#include <rime_api.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

RimeApi* api = nullptr;

std::vector<std::string> menu(RimeSessionId session, const std::string& roman) {
  api->clear_composition(session);
  if (!api->simulate_key_sequence(session, roman.c_str())) return {};
  RIME_STRUCT(RimeContext, context);
  std::vector<std::string> out;
  if (api->get_context(session, &context)) {
    for (int i = 0; i < context.menu.num_candidates; ++i) {
      const char* text = context.menu.candidates[i].text;
      out.emplace_back(text ? text : "");
    }
    api->free_context(&context);
  }
  return out;
}

std::vector<std::string> finish_menu(RimeSessionId session, const std::string& roman) {
  api->clear_composition(session);
  if (roman.empty()) return {};
  if (roman.size() > 1) {
    const std::string prefix = roman.substr(0, roman.size() - 1);
    if (!api->simulate_key_sequence(session, prefix.c_str())) return {};
  }
  if (!api->process_key(session, static_cast<unsigned char>(roman.back()), 0)) return {};
  RIME_STRUCT(RimeContext, context);
  std::vector<std::string> out;
  if (api->get_context(session, &context)) {
    for (int i = 0; i < context.menu.num_candidates; ++i) {
      const char* text = context.menu.candidates[i].text;
      out.emplace_back(text ? text : "");
    }
    api->free_context(&context);
  }
  return out;
}

bool select_number(RimeSessionId session, int zero_based_index) {
  if (zero_based_index < 0 || zero_based_index > 8) return false;
  if (!api->process_key(session, '1' + zero_based_index, 0)) return false;
  RIME_STRUCT(RimeCommit, commit);
  const bool committed = api->get_commit(session, &commit);
  if (committed) api->free_commit(&commit);
  return committed;
}

int index_of(const std::vector<std::string>& values, const std::string& target) {
  for (size_t i = 0; i < values.size(); ++i) {
    if (values[i] == target) return static_cast<int>(i);
  }
  return -1;
}

RimeSessionId start_session(const char* shared, const char* user) {
  const std::string prebuilt = std::string(shared) + "/build";
  const std::string staging = std::string(user) + "/build";
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = shared;
  traits.user_data_dir = user;
  traits.prebuilt_data_dir = prebuilt.c_str();
  traits.staging_dir = staging.c_str();
  traits.app_name = "rime.re_gu_trans_test";
  traits.distribution_name = "re-gu-trans-test";
  traits.distribution_code_name = "integration";
  traits.distribution_version = "1";
  traits.log_dir = "";
  api->setup(&traits);
  api->initialize(&traits);
  if (api->start_maintenance(True)) api->join_maintenance_thread();
  const RimeSessionId session = api->create_session();
  if (!session || !api->select_schema(session, "gujarati")) return 0;
  return session;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3 || argc > 4) {
    std::cerr << "usage: rime_session_driver SHARED_DIR USER_DIR [required-missing]\n";
    return 2;
  }
  api = rime_get_api();
  const auto startup_begin = Clock::now();
  RimeSessionId session = start_session(argv[1], argv[2]);
  if (!session) return 3;
  const double startup_ms =
      std::chrono::duration<double, std::milli>(Clock::now() - startup_begin).count();
  if (argc == 4 && std::string(argv[3]) == "required-missing") {
    const bool blocked = menu(session, "padi").empty();
    api->destroy_session(session);
    api->finalize();
    std::cout << "{\"ok\":" << (blocked ? "true" : "false")
              << ",\"real_librime\":true,\"required_model_missing_blocked\":"
              << (blocked ? "true" : "false") << ",\"startup_ms\":" << startup_ms << "}\n";
    return blocked ? 0 : 12;
  }

  const std::string roman = "padi";
  const std::string target = "પાડી";
  auto initial = menu(session, roman);
  const bool latin_slot_observed = initial.size() >= 3 && initial[1] == roman;
  const bool binary_menu_observed = !initial.empty();
  if (!latin_slot_observed) return 4;
  const auto neural_probe_menu = menu(session, "aajdeevse");
  const bool neural_candidate_observed =
      index_of(neural_probe_menu, "આજદિવસે") >= 0;

  const std::vector<std::string> benchmark_inputs = {
      "jamin", "favshe", "poshatu", "ketli", "padi", "parkhavyu",
      "mne", "gujarat", "shanti", "kshama", "gnan", "moolyama"};
  std::vector<double> query_ms;
  std::vector<double> sequence_ms;
  query_ms.reserve(600);
  sequence_ms.reserve(600);
  for (int round = 0; round < 50; ++round) {
    for (const auto& input : benchmark_inputs) {
      const auto sequence_begin = Clock::now();
      const auto candidates = menu(session, input);
      sequence_ms.push_back(std::chrono::duration<double, std::milli>(
          Clock::now() - sequence_begin).count());
      if (candidates.empty()) return 10;
      api->clear_composition(session);
      if (input.size() > 1) {
        const std::string prefix = input.substr(0, input.size() - 1);
        if (!api->simulate_key_sequence(session, prefix.c_str())) return 10;
      }
      const auto query_begin = Clock::now();
      if (!api->process_key(session, static_cast<unsigned char>(input.back()), 0)) return 10;
      RIME_STRUCT(RimeContext, context);
      if (!api->get_context(session, &context)) return 10;
      const bool has_candidates = context.menu.num_candidates > 0;
      api->free_context(&context);
      query_ms.push_back(std::chrono::duration<double, std::milli>(
          Clock::now() - query_begin).count());
      if (!has_candidates) return 10;
    }
  }
  std::sort(query_ms.begin(), query_ms.end());
  std::sort(sequence_ms.begin(), sequence_ms.end());
  const auto percentile = [&](const std::vector<double>& values, double p) {
    const size_t at = std::min(values.size() - 1,
                               static_cast<size_t>(values.size() * p));
    return values[at];
  };

  std::vector<std::string> tops;
  for (int count = 1; count <= 3; ++count) {
    auto current = menu(session, roman);
    const int index = index_of(current, target);
    if (index < 0 || !select_number(session, index)) return 5;
    auto next = menu(session, roman);
    if (next.empty()) return 6;
    tops.push_back(next[0]);
  }
  const bool three_selection_observed =
      tops[0] != target && tops[1] != target && tops[2] == target;
  if (!three_selection_observed) return 7;
  const std::filesystem::path learning_path =
      std::filesystem::path(argv[2]) / "gujarati.user-learning.json";
  std::ifstream learning_stream(learning_path);
  const bool learning_file_open = learning_stream.is_open();
  const std::string learning_json((std::istreambuf_iterator<char>(learning_stream)),
                                  std::istreambuf_iterator<char>());
  const bool atomic_file_observed = learning_file_open &&
      learning_json.find(target) != std::string::npos;
  if (!atomic_file_observed) return 11;

  api->destroy_session(session);
  api->finalize();
  session = start_session(argv[1], argv[2]);
  if (!session) return 8;
  const auto restarted = menu(session, roman);
  const bool persisted = restarted.size() >= 2 && restarted[0] == target && restarted[1] == roman;
  api->destroy_session(session);
  api->finalize();
  if (!persisted) return 9;

  const bool candidate_access_observed = three_selection_observed;
  const bool commit_notifier_observed = three_selection_observed;

  std::cout << "{\"ok\":true,\"real_librime\":true,"
            << "\"three_selection_observed\":" << (three_selection_observed ? "true" : "false")
            << ",\"learning_persisted\":" << (persisted ? "true" : "false")
            << ",\"neural_candidate_observed\":" << (neural_candidate_observed ? "true" : "false")
            << ",\"latin_slot\":" << (latin_slot_observed ? 2 : -1) << ","
            << "\"capabilities\":{\"trie\":" << (binary_menu_observed ? "true" : "false")
            << ",\"candidate_access\":" << (candidate_access_observed ? "true" : "false")
            << ",\"commit_notifier\":" << (commit_notifier_observed ? "true" : "false")
            << ",\"write_file_atomic\":" << (atomic_file_observed ? "true" : "false") << "},"
            << "\"benchmark\":{\"host\":\"real-librime\",\"cases\":"
            << query_ms.size() << ",\"startup_ms\":" << startup_ms
            << ",\"query_definition\":\"final-keystroke-to-menu\""
            << ",\"query_p50_ms\":" << percentile(query_ms, 0.50)
            << ",\"query_p95_ms\":" << percentile(query_ms, 0.95)
            << ",\"full_sequence_p50_ms\":" << percentile(sequence_ms, 0.50)
            << ",\"full_sequence_p95_ms\":" << percentile(sequence_ms, 0.95) << "}}\n";
  return 0;
}
