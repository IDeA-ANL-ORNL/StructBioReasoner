ps aux | grep 'parsl' | grep avasan | awk '{print $2}' | xargs kill -9
ps aux | grep 'python' | grep avasan | awk '{print $2}' | xargs kill -9
rm data/jnana.db
rm parsl.htex.block*
rm cmd_parsl.htex*
rm -r data/folds
rm -r data/fastas
