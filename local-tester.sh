#! /bin/bash

tests_summary="baseline-metrics.txt"
base_metrics_tmpfile="/tmp/tester.tmp1"
tested_tmpfile="/tmp/tester.tmp2"
tested_metrics_tmpfile="/tmp/tester.tmp3"

###########
# helpers #
###########

function usage {
  echo "usage: bash $0 [<test_id>]"
  echo -e "ARGS"
  echo -e "\t<test_id>: ID of the test to be run among {$(echo $test_ids | sed 's/ /,/g')}. If no ID is specified, all tests are run."
  echo "OPTIONS"
  echo -e "\t-h\tprints this help message."
  exit 0
}

function run_single_test {
  # extract info of the test to run
  testid=$1
  test_metrics=$(cat $tests_summary | awk "BEGIN{toprint=0} /Metrics for test/{toprint=0} /Metrics for test $testid/{toprint=1} {if(toprint) print}")
  cmd2run=$(echo -e "$test_metrics" | grep "Command" | sed 's/.*python3 //g' | tr -d "]")
  test_metrics=$(echo -e "$test_metrics" | egrep -v "(Metrics for test|Command)")
  echo -e "$test_metrics" > $base_metrics_tmpfile

  # try to run the command
  echo -e "\nRunning $cmd2run"
  python3 $cmd2run >$tested_tmpfile
  [[ $(echo $?) -gt 0 ]] && echo -e "Something went wrong when running the simulator\nAborting.." && exit 1

  # output comparison between metrics
  echo -e "\nProcessing results"
  [[ -f $tested_metrics_tmpfile ]] && rm $tested_metrics_tmpfile
  while IFS= read -r line; do
    tomatch="$(echo $line | sed 's/:.*//g')"
    [[ -z $(echo $tomatch | egrep "[a-z]") ]] && continue
    towrite=$(grep "$tomatch" $tested_tmpfile)
    [[ ! -f $tested_metrics_tmpfile ]] && echo -e "$towrite" > $tested_metrics_tmpfile || echo -e "$towrite" >> $tested_metrics_tmpfile
  done < $base_metrics_tmpfile
  echo -e "Diff between baseline metrics (on the left) and tested solution (on the right)"
  diff -B -y $base_metrics_tmpfile $tested_metrics_tmpfile
}

########
# main #
########

test_ids="A1 A2 A3 B1 B2 B3 C1 C2 C3 C4"

# parse options and arguments
while getopts "h" opt; do
  case "$opt" in
  h)
    usage
    exit 0
    ;;
  esac
done
shift $((OPTIND -1))

[[ $# -gt 2 ]] && usage && exit 1
[[ $# -gt 0 ]] && [[ -z $(echo $test_ids | grep "$1") ]] && echo -e "\nERROR: unknown test ID\n" && usage && exit 1
[[ $# -gt 0 ]] && test_ids=$1

# position in the directory of this script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR

# remove previous files (if any)
for file in $base_metrics_tmpfile $tested_tmpfile $tested_metrics_tmpfile; do
  [[ -f $file ]] && rm $file
done

# run tests
for testid in $test_ids; do
  run_single_test $testid
done

