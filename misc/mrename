#! /usr/bin/env perl

=pod

INPUT SOURCE
    file
    STDIN
    ARGV
    clipboard
    glob()

INPUT STRUCTURE
    Classic:        perl_expression  ORIG
    Concatendated:  orig1 orig2 ... new1 new2 ...
    Delimited:      orig1-new1 orig2-new2 ...
    Explicit:       --original orig1 orig2 ...
                    --new      new1  new2  ...

TRANSFORMATIONS
    eval(perl_expression)
    file name patterns
    remove common leading/trailing text

INPUT FILTERS
    files only
    dirs only
    filtering code: retain item if code returns true

OPTIONS
    dryrun
    backup
    interactive
    strict
    verbose
    copy_mode
    link_mode

=cut

use strict;
use warnings;
use feature qw(say);


################################################################

package GetterSetter;

sub getset {
    my ($self, $k, $v) = @_;
    $self->{$k} = $v if @_ > 2;
    $self->{$k};
}


################################################################

package Renaming;

our @ISA = qw(GetterSetter);
use File::Spec::Functions qw(splitpath catdir canonpath);
use Data::Dumper qw(Dumper);
sub xxx { print Dumper(@_) }

sub new {
    my ($class, %args) = @_;
    my %DEFAULTS = (
        old_name => undef,
        new_name => undef,
        new_dir  => undef,
    );
    %args = (%DEFAULTS, %args);
    bless \%args, $class;
}

sub determine_new_dir {
    my $self = shift;
    my ($vol, $dirs, $file) = File::Spec->splitpath($self->new_name);
    # $dirs = canonpath($dirs);
    # $vol  = canonpath($vol);
    # xxx [$vol, $dirs, $file];
    $self->new_dir( $vol  eq '' ? $dirs :
                    $dirs eq '' ? $vol  : catdir($vol, $dirs) );
}

sub old_name { shift->getset('old_name', @_) }
sub new_name { shift->getset('new_name', @_) }
sub new_dir  { shift->getset('new_dir',  @_) }

################################################################

package Renamer;

use File::Basename qw(basename);

our @ISA = qw(GetterSetter);
use Data::Dumper qw(Dumper);
sub xxx { print Dumper(@_) }

use Getopt::Long qw(GetOptionsFromArray);

__PACKAGE__->run(@ARGV) unless caller;

sub usage {
    my $self = shift;
    my $script = basename($0);
    my $usage = "
        Usage:
            $script PERL_EXPRESSION OLD_NAMES        # Old names.

        This script renames files.

        Options:
            --dryrun        Print renamings, but do not execute them.
            --help

        Future Usage:
            $script --delimiter X   OLD_NEW_NAMES    # Delimited old-new pairs.

        Future options:
            --delimiter X
            --confirm
    ";
    $usage =~ s/\n {8}/\n/g;
    print $usage;
    exit;
}

sub run {
    my $class = shift;
    my $self = $class->new;
    $self->get_options(@_);
    $self->usage if $self->help;
    $self->get_orig_file_names;
    $self->set_new_file_names;
    $self->prune_renamings;
    $self->check_for_non_unique_new_names;
    $self->check_for_collisions;
    $self->check_dirs_of_new_names;
    $self->rename_files;
}

sub get_options {
    my $self = shift;
    my %opt = (
        'help'      => 0,
        'dryrun'    => 0,
        'confirm'   => 0,
        'delimiter' => undef,
    );
    GetOptionsFromArray(\@_, \%opt,
        'help',
        'dryrun',
        'confirm',
        'delimiter=s',
    );
    $self->{$_} = $opt{$_} for keys %opt;
    $self->{args} = [ @_ ];
}

sub get_orig_file_names {
    my $self = shift;
    if (defined $self->delimiter){
        die "The --delimiter option is not supported yet.\n";
    }
    else {
        my @args = @{delete $self->{args}};
        $self->usage unless @args > 1;
        $self->{perl_expr} = shift @args;
        $self->{renamings} = [ map { Renaming->new(old_name => $_) } @args ];
    }
}

sub set_new_file_names {
    my $self = shift;
    my $perl_expr = $self->perl_expr;
    my @new_file_names;
    for my $rn ($self->renamings){
        local $_ = $rn->old_name;
        eval $perl_expr;
        die $@ if $@;
        $rn->new_name($_);
    }
}

sub prune_renamings {
    my $self = shift;
    $self->{renamings} = [ grep { $_->old_name ne $_->new_name } $self->renamings ];
}

sub new {
    my $class = shift;
    my $self = {};
    bless $self, $class;
}

sub check_for_non_unique_new_names {
    my $self = shift;
    my %seen;
    for my $rn ($self->renamings){
        my ($old, $new) = ($rn->old_name, $rn->new_name);
        # TODO: should not die here.
        die "Duplicate new name: $old => $new\n" if exists $seen{$new};
        $seen{$new} = 1; 
    }
}

sub check_for_collisions {
    my $self = shift;
    for my $rn ($self->renamings){
        my ($old, $new) = ($rn->old_name, $rn->new_name);
        # TODO: should not die here.
        die "Item with new name already exists: $old => $new\n" if -e $new;
    }
}

sub check_dirs_of_new_names {
    my $self = shift;
    for my $rn ($self->renamings){
        my ($old, $new) = ($rn->old_name, $rn->new_name);
        $rn->determine_new_dir;
        my $d = $rn->new_dir;
        next unless length $d;
        # TODO: should not die here.
        #       simply accumulate errors.
        #       We might be in dryrun mode and simple want to print stuff.
        die "Directory needed by new name does not exist: $old => $new ($d)\n" unless -d $d;
    }
}

sub rename_files {
    my $self = shift;

    if ($self->dryrun) {
        for my $rn ($self->renamings){
            my ($old, $new) = ($rn->old_name, $rn->new_name);
            say '';
            say $old;
            say $new;
        }

        # TODO: print errors accumulated above.

    }
    else {
        for my $rn ($self->renamings){
            my ($old, $new) = ($rn->old_name, $rn->new_name);
            rename $old, $new;
        }
    }
}

sub help      { shift->getset('help',      @_) }
sub dryrun    { shift->getset('dryrun',    @_) }
sub confirm   { shift->getset('confirm',   @_) }
sub delimiter { shift->getset('delimiter', @_) }
sub perl_expr { shift->getset('perl_expr', @_) }
sub renamings { @{shift->{renamings}} }


