module.exports = {
  apps: [{
    name: 'arena-referee',
    script: 'engine/run_turn.py',
    interpreter: 'python3',
    cwd: '/home/hlnx4/arena',
    cron_restart: '*/30 * * * *',
    autorestart: false,
    watch: false,
    max_restarts: 0,
    env: {
      PYTHONPATH: '/home/hlnx4/arena:/home/hlnx4/projects/void_pulse',
    },
    error_file: '/home/hlnx4/arena/state/pm2_error.log',
    out_file: '/home/hlnx4/arena/state/pm2_out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
  }]
};
