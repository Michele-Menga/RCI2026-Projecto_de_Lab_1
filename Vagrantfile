

nodes = {
  "boot" => "192.168.56.21",
  "no1"  => "192.168.56.11",
  "no2"  => "192.168.56.12",
  "no3"  => "192.168.56.13"
}

Vagrant.configure("2") do |config|
  config.ssh.insert_key = false
  config.vbguest.auto_update = false if Vagrant.has_plugin?("vagrant-vbguest")

  nodes.each do |name, ip|
    config.vm.define name do |m|
      m.vm.box = "ubuntu/trusty64"
      m.vm.hostname = name
      m.vm.network "private_network", ip: ip
      m.vm.provider "virtualbox" do |vb|
        vb.name = name
        vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
        vb.memory = "256"
      end
    end
  end
end